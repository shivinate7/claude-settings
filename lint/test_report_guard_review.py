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
  The newest record decides. The check takes merge's verdict, never a PASS word of its own.
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
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import test_report_guard as trg  # noqa: E402  the Stop runner, transcript records and run folder (one home)
import merge as merge_mod  # noqa: E402  the review record's form and parser (one home, merge/merge.py)

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


def record(head=LIVE, n=PR, rounds=ROUNDS, fix=None):
    """A review record comment, in merge/merge.py's own form: Kind normal, Guard or check no, Net value not owed."""
    return merge_mod.review_body(n, head, "normal", "no", rounds, "not owed", fix)


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

    def serve(self, comments=(), fail_pulls=None, fail_comments=None, prs=None):
        """The stand-in's answers: each PR's live head and its comments, oldest first, and any read to break.
        `prs` maps a PR number to {"head": sha, "comments": [bodies]}; without it, PR 12 has `comments`."""
        if prs is None:
            prs = {PR: {"head": LIVE, "comments": list(comments)}}
        state = {"prs": {str(n): {"head": p["head"], "comments": list(p["comments"])} for n, p in prs.items()},
                 "count_file": self.count, "fail_pulls": fail_pulls, "fail_comments": fail_comments}
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


if __name__ == "__main__":
    unittest.main()
