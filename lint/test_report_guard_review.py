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
  such a claim in a lane. A failed read, or an exception in the check, never blocks: the reply gets a systemMessage
  with UNKNOWN, never "clear".
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
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import test_report_guard as trg  # noqa: E402  the Stop runner, transcript records and run folder (one home)
import merge as merge_mod  # noqa: E402  the review record's form and parser (one home, merge/merge.py)
import report_guard as rg  # noqa: E402  the Stop hook's review check, run in this process for the budget cases (one home)
import guard_merge  # noqa: E402  the merge tool's loader: the check's merge module is the one the budget cases patch
import _nowindow  # noqa: E402  the one no-window child start, where every read of the check goes

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
# the state names; any other number is a 404. A list read pages as gh does: 30 items a page unless per_page says
# more (at most 100), one page unless --paginate. --paginate joins the pages into one array, and --paginate --slurp
# prints an array of the pages. This follows listing() in hooks/test_guard.py, the repo's model of gh. Real gh's
# bare --paginate output is not measured here.
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
commit = re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?commits/([0-9a-f]{40})", path)
compare = re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?compare/(.+)", path)
if pull:
    if state["fail_pulls"]:
        fail(state["fail_pulls"])
    number = pull.group(1)
    if number not in state["prs"]:
        not_found()
    print(json.dumps({"number": int(number), "state": "open", "draft": False,
                      "head": {"sha": state["prs"][number]["head"], "ref": "feat-" + number}, "base": {"ref": "main"}}))
elif issue:
    if state["fail_comments"]:
        fail(state["fail_comments"])
    number = issue.group(1)
    if number not in state["prs"]:
        not_found()
    comments = [{"id": k + 1, "body": body, "issue_url": "https://api.github.com/repos/example-owner/example-repo/issues/" + number}
                for k, body in enumerate(state["prs"][number]["comments"])]
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
elif commit:
    sha = commit.group(1)
    if sha not in state["commits"]:
        not_found()
    spec = state["commits"][sha]
    print(json.dumps({"sha": sha, "parents": [{"sha": p} for p in spec["parents"]], "commit": {"tree": {"sha": spec["tree"]}}}))
elif compare:
    print(json.dumps({"status": state["compares"].get(compare.group(1), "diverged")}))
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


def report(done):
    """A report with `done` as its Done item. The other three items hold nothing a check reads."""
    return "\n".join(["> **Done** " + done, "> **Deviations** none", "> **Input Needed** none", "> **Next** wait"])


def record(head=LIVE, n=PR, rounds=ROUNDS, fix=None, guard="no", net="not owed"):
    """A review record comment, in merge/merge.py's own form: Kind normal, Guard or check and Net value as given."""
    return merge_mod.review_body(n, head, "normal", guard, rounds, net, fix)


# The incident (pull request 2189, comment 6726184510): a valid record at its live head, with a note line after its CI line.
INCIDENT_PR, INCIDENT_HEAD = 2189, "d35865d42dae16eef06d9cc516c56f904c287fe1"
INCIDENT_ROUNDS = [(1, "reviewer", "haiku", "FAIL"), (2, "reviewer", "sonnet", "PASS"), (3, "reviewer", "sonnet", "PASS")]
INCIDENT_FIX = ("5acce9e26c7520dc8808304f87dfeb6805192300", "reviewer", "sonnet", "PASS")
INCIDENT_NOTE = 'Note, Fix: none, Until: 2026-11-21: the remedy says "copy your edited files aside"; on real git a copy leaves the file in place.'
FOOTER = "\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_\n"  # the footer a GitHub post carries


def incident(note):
    """The incident's comment: the record, then the note line after a blank line when `note`, then the footer."""
    body = record(head=INCIDENT_HEAD, n=INCIDENT_PR, rounds=INCIDENT_ROUNDS, fix=INCIDENT_FIX, guard="yes", net="positive")
    return body.rstrip("\n") + ("\n\n" + INCIDENT_NOTE if note else "") + FOOTER


class FakeClock:
    """The clock of the review check, when the check runs in this process. Each gh call takes `seconds` of fake time; a call longer than its
    timeout ends at that timeout, as subprocess.run does. A local git call takes no fake time. `now` is the only clock the check's deadlines read,
    and no assert reads the real clock."""

    def __init__(self, seconds, answer):
        self.now, self.seconds, self.answer, self.gh_calls = 0.0, seconds, answer, []
        self.real_run = _nowindow.run  # captured before a case patches it

    def monotonic(self):
        return self.now

    def time_module(self):
        """A stand-in for merge/merge.py's `time`: its deadlines read `now`, and nothing sleeps."""
        return types.SimpleNamespace(monotonic=self.monotonic, time=lambda: self.now, sleep=lambda s: None)

    def run(self, args, **kw):
        if os.path.basename(args[0]) not in ("gh", "gh.exe"):
            return self.real_run(args, **kw)
        self.gh_calls.append(list(args))
        timeout = kw.get("timeout")
        if timeout is not None and self.seconds > timeout:
            self.now += timeout
            raise subprocess.TimeoutExpired(args, timeout)
        self.now += self.seconds
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(self.answer(args)), stderr="")


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
        write_fake_gh(self.gh_dir)
        self.assertIsNotNone(shutil.which("gh", path=self.gh_dir), "the stand-in gh is not on its own PATH")
        self.serve()

    def serve(self, comments=(), fail_pulls=None, fail_comments=None, prs=None, commits=None, compares=None):
        """The stand-in's answers: each PR's live head and its comments, oldest first, and any read to break.
        `prs` maps a PR number to {"head": sha, "comments": [bodies]}; without it, PR 12 has `comments`. `commits` maps a sha to
        {"parents": [shas], "tree": sha}, the commit read's answer; `compares` maps "<head>...<base>" to the status compare gives."""
        if prs is None:
            prs = {PR: {"head": LIVE, "comments": list(comments)}}
        state = {"prs": {str(n): {"head": p["head"], "comments": list(p["comments"])} for n, p in prs.items()},
                 "count_file": self.count, "fail_pulls": fail_pulls, "fail_comments": fail_comments,
                 "commits": dict(commits or {}), "compares": dict(compares or {})}
        with open(os.path.join(self.gh_dir, "state.json"), "w", encoding="utf-8") as handle:
            json.dump(state, handle)

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

    def stop(self, records, env_id=True, script=None, block=()):
        """Run the Stop hook on `records`. env_id is this session's remote id (a lane sets it). The stand-in
        comes first on PATH, and the call log is emptied first, so each run's calls are its own. `script` runs
        another copy of the hook, and `block` names modules the run cannot import."""
        open(self.count, "w", encoding="utf-8").close()
        path = trg.write_transcript(records, self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": self.repo}
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

    def assert_blocked(self, out):
        self.assertIsNotNone(out, "the reply passed; expected a block")
        self.assertEqual(out.get("decision"), "block", out)
        self.assertTrue(out.get("reason"), out)

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

    def assert_open_guard_record_blocks_with_its_why(self, body):
        """A PASS claim on a record that merge reads open is refused. The reason carries review_state's why for the live head, and it
        does not tell the lane to post a record, since the record is posted already."""
        state, why = merge_mod.review_state(merge_mod.parse_review(body), LIVE)
        self.assertEqual(state, "open", "fixture: merge/merge.py does not call this record open")
        self.serve(comments=[body])
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertIn(why, out["reason"], f"the refusal does not carry review_state's why {why!r}: {out['reason']}")
        self.assertNotIn("has no review record", out["reason"], "the refusal says there is no review record, but the record is posted")
        self.assertNotIn("--review-record", out["reason"], "the refusal tells the lane to post a record that is already posted")
        self.assertNotIn("post the record", out["reason"], "the refusal tells the lane to post a record that is already posted")

    def test_guard_yes_record_that_reads_open_blocks_a_pass_claim_with_its_why(self):
        # Catches: a PASS claim on an open record refused with the no-record remedy, which tells the lane to post a record already on the PR.
        # Each record reads open: a fix check PASS after a failed round 1 or 2 owes round 3 and its net value (owner ruling r9, 14:01 CST), a final
        # round FAIL owes its net value, and a design reviewer FAIL keeps a first-round PASS open, fix verifier or not.
        fix = (OLD, "reviewer", "sonnet", "PASS")
        cases = (([(1, "reviewer", "sonnet", "FAIL")], fix),
                 ([(1, "reviewer", "sonnet", "FAIL"), (2, "reviewer", "sonnet", "FAIL")], fix),
                 ([(1, "reviewer", "sonnet", "FAIL"), (2, "reviewer", "sonnet", "FAIL"), (3, "reviewer", "opus", "FAIL")], None),
                 ([(1, "reviewer", "sonnet", "PASS"), (1, "design-reviewer", "opus", "FAIL")], fix))
        for rounds, fix_line in cases:
            with self.subTest(rounds=rounds, fix=fix_line):
                self.assert_open_guard_record_blocks_with_its_why(record(rounds=rounds, guard="yes", net="not owed", fix=fix_line))

    def test_guard_yes_record_with_a_passing_fix_verifier_or_round_three_is_not_refused(self):
        # A passing fix verifier after a passed round ends a guard or check change (owner ruling r9, 14:01 CST). A passing final round does too,
        # with no net value owed, so each PASS claim here is satisfied and not refused
        fix = (OLD, "reviewer", "sonnet", "PASS")
        cases = (([(1, "reviewer", "sonnet", "PASS")], fix),
                 ([(1, "reviewer", "sonnet", "FAIL"), (2, "reviewer", "sonnet", "FAIL"), (3, "reviewer", "opus", "PASS")], None))
        for rounds, fix_line in cases:
            with self.subTest(rounds=rounds, fix=fix_line):
                self.assert_record_satisfies_claim(record(rounds=rounds, guard="yes", net="not owed", fix=fix_line))

    def test_guard_yes_record_that_passes_before_the_final_round_with_no_fix_check_is_not_refused(self):
        # control: owner, page item 471 a: merge reads a guard or check change whose round passed, with no fix check, as done before the
        # final round, so the claim passes on two reads
        cases = ([(1, "reviewer", "sonnet", "PASS")],
                 [(1, "reviewer", "sonnet", "PASS"), (2, "reviewer", "sonnet", "PASS")],
                 [(1, "reviewer", "sonnet", "FAIL"), (2, "reviewer", "sonnet", "PASS")])
        for rounds in cases:
            with self.subTest(rounds=rounds):
                self.assert_record_satisfies_claim(record(rounds=rounds, guard="yes", net="not owed"))

    def test_no_record_keeps_the_no_record_remedy(self):
        # control: with no record for the live head, the refusal keeps the remedy that posts one
        self.serve()
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_reads_of(PR)
        self.assert_blocked(out)
        self.assertIn("has no review record", out["reason"], out)
        self.assertIn("merge 12 --review-record", out["reason"], out)

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

    # Clean merges of main keep a record (decision pr-review-record). The check reads the merge through merge/merge.py.

    def git_in_repo(self, *args):
        """Run git in this run's repo, with a fixed identity. -> its stdout, stripped. A failed command fails the case."""
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        run = subprocess.run(["git", "-C", self.repo, "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, env=env)
        self.assertEqual(run.returncode, 0, "git %s failed: %s" % (" ".join(args), run.stderr))
        return run.stdout.strip()

    def commit_file(self, path, text, message):
        """Write `path` in this run's repo and commit it. -> the new commit's sha. A commit during a merge completes that merge."""
        with open(os.path.join(self.repo, path), "w", encoding="utf-8") as handle:
            handle.write(text)
        self.git_in_repo("add", path)
        self.git_in_repo("commit", "-q", "-m", message)
        return self.git_in_repo("rev-parse", "HEAD")

    def clean_merge_repo(self, edited=False):
        """Commits in this run's repo: `old`, the reviewed head, and `main`, a commit on a branch off the same root. `live` merges the two: git's own
        clean merge, or with one file more when `edited`. -> the shas by name, with `commits` and `compares` in the form serve() takes."""
        root = self.commit_file("root.txt", "root\n", "root")
        self.git_in_repo("checkout", "-q", "-b", "feat")
        old = self.commit_file("a.txt", "a\n", "reviewed head")
        self.git_in_repo("checkout", "-q", "-b", "side", root)
        main = self.commit_file("b.txt", "b\n", "main")
        self.git_in_repo("checkout", "-q", "feat")
        if edited:
            self.git_in_repo("merge", "-q", "--no-ff", "--no-commit", "side")
            live = self.commit_file("x.txt", "x\n", "merge of main, with one edit")
        else:
            self.git_in_repo("merge", "-q", "--no-ff", "--no-edit", "side")
            live = self.git_in_repo("rev-parse", "HEAD")
        commits = {}
        for sha in (root, old, main, live):
            parents = self.git_in_repo("rev-list", "--parents", "-n", "1", sha).split()[1:]
            commits[sha] = {"parents": parents, "tree": self.git_in_repo("rev-parse", sha + "^{tree}")}
        git_tree = subprocess.run(["git", "-C", self.repo, "merge-tree", "--write-tree", old, main], capture_output=True, text=True).stdout.split()[:1]
        if edited:
            self.assertNotEqual(git_tree, [commits[live]["tree"]], "fixture: the edited merge has git's clean merge tree")
        else:
            self.assertEqual(git_tree, [commits[live]["tree"]], "fixture: git's merge of old and main is not the live merge's tree")
        return {"old": old, "main": main, "live": live, "commits": commits, "compares": {f"{main}...main": "ahead"}}

    def serve_merge(self, merged):
        """The stand-in serves pull request 12 at the merge's live head, with a record for its reviewed head, and the merge's commits and compares."""
        self.serve(prs={PR: {"head": merged["live"], "comments": [record(head=merged["old"])]}}, commits=merged["commits"],
                   compares=merged["compares"])

    def test_clean_main_merge_after_the_reviewed_head_does_not_block(self):
        # Catches: a clean merge of main after the reviewed head read stale, so a PASS claim on its PR is refused.
        self.serve_merge(self.clean_merge_repo())
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assertIsNone(out, "a clean merge of main after the reviewed head blocked the PASS claim: %r" % (out,))

    def test_edited_merge_of_main_after_the_reviewed_head_still_blocks(self):
        # Control: the same merge with one file more than git's clean merge reads stale, so the claim is still refused.
        self.serve_merge(self.clean_merge_repo(edited=True))
        out = self.stop(self.lane_turn(report(CLAIM)))
        self.assert_blocked(out)
        self.assertIn("PR #12", out["reason"], out)

    def test_a_clean_merge_read_is_one_commit_read_and_one_compare(self):
        # Catches: the check reading a clean merge with more routes than its PR reads, its commit read and its compare, or with fewer.
        merged = self.clean_merge_repo()
        self.serve_merge(merged)
        self.stop(self.lane_turn(report(CLAIM)))
        routes = sorted(a.split("?", 1)[0].split("/", 3)[3] for argv in self.gh_calls() for a in argv if a.startswith("repos/"))
        expected = sorted([f"pulls/{PR}", f"issues/{PR}/comments", f"commits/{merged['live']}", f"compare/{merged['main']}...main"])
        self.assertEqual(routes, expected, "the check read %r, not the two PR reads, one commit read and one compare" % (routes,))

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

    # The budget: the check ends inside the Stop hook's timeout. The hook is killed at that timeout and prints no block.

    def hook_budget(self):
        """The Stop hook's timeout for lint/report_guard.py, read from settings.json: the budget a hook run is killed at."""
        with open(os.path.join(HERE, "..", "settings.json"), encoding="utf-8") as handle:
            settings = json.load(handle)
        for entry in settings["hooks"]["Stop"]:
            for hook in entry["hooks"]:
                if "/lint/report_guard.py" in hook["command"]:
                    return hook["timeout"]
        self.fail("settings.json holds no Stop hook for lint/report_guard.py")

    def review_check_on_fake_clock(self, seconds, numbers=(PR,)):
        """-> (refusal, note, elapsed, gh_calls): the review check of a lane's PASS claim on each PR in `numbers`, run in this process on a FakeClock
        whose every gh call takes `seconds`. Each PR's newest record is for an earlier head, so the check runs that PR's clean-merge walk: the live
        head's commit read, then its parent's. The parent's tree differs, so each record stays stale and each PR's claim is refused."""
        parent = "2b" * 20
        trees = {LIVE: "3c" * 20, parent: "4d" * 20}
        parents = {LIVE: [parent], parent: []}

        def answer(args):
            route = next(a for a in args if re.search(r"/(pulls|issues|commits|compare)/", a))
            pull = re.search(r"/pulls/(\d+)$", route)
            if pull:
                return {"head": {"sha": LIVE}}
            issue = re.search(r"/issues/(\d+)/comments$", route)
            if issue:
                return [[{"body": record(head=OLD, n=int(issue.group(1)))}]]
            if "/commits/" in route:
                sha = route.rsplit("/", 1)[1]
                return {"sha": sha, "parents": [{"sha": p} for p in parents[sha]], "commit": {"tree": {"sha": trees[sha]}}}
            return {"status": "diverged"}

        claim = "OTHER: round 2 PASS on " + " and ".join("PR #%d" % n for n in numbers) + "."
        clock = FakeClock(seconds, answer)
        path = trg.write_transcript(self.lane_turn(report(claim)), self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "cwd": self.repo}
        merge_tool = guard_merge.merge_module()
        self.assertIsNotNone(merge_tool, "fixture: merge/merge.py does not load")
        # Every clock the check reads is the fake one: the merge tool's, and the process's, for a read in report_guard.py.
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE_SESSION_ID": LANE_ENV}), \
                mock.patch.object(_nowindow, "run", clock.run), \
                mock.patch("time.monotonic", clock.monotonic), \
                mock.patch.object(merge_tool, "time", clock.time_module()):
            refusal, note = rg.review_record_problem(hook, report(claim))
        return refusal, note, clock.now, clock.gh_calls

    def test_slow_gh_reads_keep_the_review_check_inside_the_hook_budget(self):
        # Catches: the walk's deadline starting only after the two reads of each PR, so slow reads of stale records run the check past the Stop
        # hook's timeout. The hook is killed there and prints no block, so the check must end inside that timeout. One claimed PR and two
        # claimed PRs: the budget is for the whole check of a claim, not for each PR. The verdict must still block, or say UNKNOWN: never a silent pass.
        budget = self.hook_budget()
        for numbers in ((PR,), (PR, PR + 1)):
            with self.subTest(claimed=numbers):
                refusal, note, elapsed, calls = self.review_check_on_fake_clock(rg.REVIEW_READ_TIMEOUT, numbers)
                self.assertTrue(any("/commits/" in a for argv in calls for a in argv),
                                "the check did not reach the clean-merge walk, so its slow reads test nothing: %r" % (calls,))
                self.assertTrue(("PR #%d" % PR) in (refusal or "") or "unknown" in (note or "").lower(),
                                "the slow check passed PR #%d with neither a block nor an UNKNOWN note: %r / %r" % (PR, refusal, note))
                self.assertLessEqual(elapsed, budget,
                                     "the review check ran %.2f s on the fake clock, past the %d s Stop hook budget" % (elapsed, budget))

    def test_fast_reads_reach_the_walk_and_block_inside_the_hook_budget(self):
        # Control: the same stale records with reads that take no time reach each walk and block each claimed PR, so the time of the slow case
        # is its reads'.
        refusal, _note, elapsed, calls = self.review_check_on_fake_clock(0, (PR, PR + 1))
        self.assertTrue(any("/commits/" in a for argv in calls for a in argv),
                        "the check did not reach the clean-merge walk: %r" % (calls,))
        for n in (PR, PR + 1):
            self.assertIn("PR #%d" % n, refusal or "", "the stale record of PR #%d did not block its PASS claim: %r" % (n, refusal))
        self.assertLessEqual(elapsed, self.hook_budget(), "the fast check ran past the Stop hook budget: %.2f s" % elapsed)


if __name__ == "__main__":
    unittest.main()
