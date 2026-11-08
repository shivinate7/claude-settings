#!/usr/bin/env python3
"""The cannot-claim check of report_guard.py (rule output-never-hand-off-doable-step), run at Stop.

A reply line that says an act cannot be done passes only when this turn holds a failed try of that act, or the line
carries a hand-off cite (a route row that says refused or asks, a dated `(measured ...)`, or a tool the session's
classifier refused), and the line names its check: a backtick span, an MCP tool name, a word such as returned or
refused, an HTTP 4xx, or a non-zero exit. A notice is no try, and a try before the last human message is no try. A
Why yours line belongs to the hand-off guard, so this check skips it.

Each case runs the Stop hook as a subprocess, as the other report_guard suites do. The Stop runner, the transcript
records and the run folder come from lint/test_report_guard.py, and the route-row seam from hooks/test_refusal_note.py,
the one homes. This file adds only its cases. Run with:

    python3 lint/test_report_guard_cannot.py -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the Stop runner, the transcript records and the run folder (one home)
import test_refusal_note as hook_base  # noqa: E402  the route-row seam and the surface pin (one home)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies the tracked lint and hooks folders, so an installed copy needs no file list

HEAD = "Cannot-claim guard (rule output-never-hand-off-doable-step)"
NO_TRY = "no failed try"
NO_CHECK = "names no check"
OPEN_PR = "mcp__github__create_pull_request"
REFUSED_ROW_ID = "r-archive"
ROW_REFUSED = hook_base.route_row(REFUSED_ROW_ID, "archive_session", "refused", surface="local")
# Words a remedy must not name: the act a refusal is about (git-remedy-never-names-target).
ACT_WORDS = re.compile(r"\bPR\b|pull request|\bopen\b|\bpush\b|\bmerge\b|\bgit\b|\bgh\b|mcp__", re.I)
# The weren't forms of the be-form claims, with straight and curly apostrophes. Two cases build lines from them.
WEREN_T_CLAIMS = ("We weren't able to merge PR 12", "We weren’t able to merge PR 12",
                  "We weren't allowed to merge PR 12", "We weren’t allowed to merge PR 12",
                  "We weren't going to be able to merge PR 12", "We weren’t going to be able to merge PR 12")


# Runs report_guard.py as the Stop hook runs it, and writes to stderr the paths its process opened (the audit event
# "open"), so a case can count the reads the check makes.
OPENS_CODE = (
    "import json, runpy, sys\n"
    "opened = []\n"
    "sys.addaudithook(lambda event, args: opened.append(args[0])"
    " if event == 'open' and args and isinstance(args[0], str) else None)\n"
    "try:\n"
    "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
    "except SystemExit:\n"
    "    pass\n"
    "sys.stderr.write('OPENED ' + json.dumps(opened) + '\\n')\n"
)


# Runs report_guard.py as the Stop hook runs it, and writes to stderr the number of builtin calls the run made (the c_call
# events of sys.setprofile). The count is the same on every run of one code, so a case that compares two sizes reads no clock.
CALLS_CODE = (
    "import json, runpy, sys\n"
    "calls = [0]\n"
    "def count(frame, event, arg):\n"
    "    if event == 'c_call':\n"
    "        calls[0] += 1\n"
    "sys.setprofile(count)\n"
    "try:\n"
    "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
    "except SystemExit:\n"
    "    pass\n"
    "sys.setprofile(None)\n"
    "sys.stderr.write('CALLS ' + str(calls[0]) + '\\n')\n"
)


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR, the model stub and the missing route-rows seam


def tearDownModule():
    trg.tearDownModule()


def use(name, input_=None, tid="tu_1"):
    """An assistant tool call. Its result pairs to it by `tid`."""
    return trg.tool_use_msg(name, input_, id_=tid)


def done(tid="tu_1", content="ok", error=False):
    """The tool result for call `tid`. `error` sets is_error; the content can carry a failure by its text."""
    return trg.tool_result_msg(tid, content=content, is_error=error)


def failed_pr_create(tid="tu_pr"):
    """A failed call to the GitHub MCP create-PR tool, a landing tool, so the turn it sits in lands."""
    return [use(OPEN_PR, {"title": "t", "head": "b", "base": "main"}, tid),
            done(tid, "HTTP 422 Validation Failed: head is invalid", error=True)]


def failed_bash(command, tid="tu_b", error=True):
    """A Bash call that exits 1. `error` False leaves the failure to the result text alone."""
    return [use("Bash", {"command": command}, tid), done(tid, "Exit code 1\nfatal: failed", error=error)]


def exit_bash(command, code, tid="tu_x"):
    """A Bash call that exits with `code`, as the shell result reports it: the exit line and the error flag."""
    return [use("Bash", {"command": command}, tid), done(tid, "Exit code %d\nerror" % code, error=True)]


def ok_bash(command, tid="tu_o"):
    return [use("Bash", {"command": command}, tid), done(tid)]


def notice(text):
    """A notice record, as Claude Code writes one. It is not a turn start and not a tool call."""
    return {"type": "attachment", "isSidechain": False, "attachment": {"type": "mcp_status", "text": text}}


def landed_reply(text):
    """A reply on a landed turn: the claim lines above the good report, which ends the reply."""
    return trg.assistant_text(text + "\n\n" + trg.GOOD_REPORT)


def input_report(first, *more):
    """A report whose Input Needed item holds `first`, with `more` as its continuation lines."""
    lines = ["> **Done** BUILT abc123", "> **Deviations** none", "> **Input Needed** " + first]
    lines += ["> " + line for line in more]
    return "\n".join(lines + ["> **Next** wait"])


class CannotClaimTests(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        self.cfg = os.path.join(self.run_dir, "cfg")
        self.home = os.path.join(self.run_dir, "home")
        self.rows = os.path.join(self.run_dir, "route_rows.json")
        os.makedirs(self.cfg)
        os.makedirs(self.home)

    # ---- the Stop run and its verdict

    def stop(self, records, active=False, refused=(), rows=(), guard=trg.REPORT_GUARD):
        """The Stop decision for `records`, or None. The route-rows file and the refusals file sit in this case's
        folder, and the surface is pinned to local so a row's outcome reads on it. `guard` is the script run; a case
        that runs an installed copy passes that copy's report_guard.py."""
        hook_base.write_route_rows(self.rows, list(rows))
        hook = {"hook_event_name": "Stop", "transcript_path": trg.write_transcript(records, self.run_dir),
                "stop_hook_active": active, "cwd": self.run_dir}
        if refused:
            hook["session_id"] = "cannot-sid-1"
            path = os.path.join(self.cfg, "state", "refusals", "cannot-sid-1.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                for tool in refused:
                    handle.write(json.dumps({"ts": "2026-11-06T10:00:00-06:00", "tool_name": tool,
                                             "reason": "refused"}) + "\n")
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env[hook_base.ROUTE_ROWS_ENV] = self.rows
        run = trg.run_guard(guard, hook, env=hook_base.surface_env(env, "local"))
        self.assertEqual(run.returncode, 0, "the Stop hook exited non-zero: " + run.stderr[-300:])
        self.assertNotIn("Traceback", run.stderr, "the Stop hook crashed: " + run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    # ---- the assertions

    def assert_blocked_for(self, out, variant, line):
        """A block that is the cannot-claim guard, on `variant`, and that lists `line`. Returns the reason."""
        self.assertIsNotNone(out, "no block came for %r" % line)
        self.assertEqual(out.get("decision"), "block", "not a block: %s" % out)
        reason = out.get("reason", "")
        self.assertIn(HEAD, reason, "the block is not the cannot-claim guard: %s" % reason)
        self.assertIn(variant, reason, "the wrong variant for %r: %s" % (line, reason))
        self.assertNotIn(NO_CHECK if variant == NO_TRY else NO_TRY, reason, "two variants in one reason: %s" % reason)
        self.assertIn(line, reason, "the claim line is not listed: %s" % reason)
        return reason

    def assert_remedy_names_no_act(self, reason):
        self.assertIn("Remedy:", reason)
        self.assertIn("Lines:", reason)
        self.assertLess(reason.index("Remedy:"), reason.index("Lines:"), "the remedy follows the lines: %s" % reason)
        remedy = reason[reason.index("Remedy:"):reason.index("Lines:")]
        self.assertNotRegex(remedy, ACT_WORDS, "the remedy names the act it refuses: %s" % remedy)

    def assert_passes(self, out, case):
        self.assertIsNone(out, "%s was refused: %s" % (case, out and out.get("reason")))

    def reply_run(self, text, code=None, timeout=15):
        """The Stop run on one reply, with no refusals file and no route rows. `code`, when given, wraps report_guard.py
        as OPENS_CODE and CALLS_CODE do; else the Stop hook runs as it is. Returns the finished process."""
        hook_base.write_route_rows(self.rows, [])
        transcript = trg.write_transcript([trg.human("open a PR"), trg.assistant_text(text)], self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": transcript, "stop_hook_active": False, "cwd": self.run_dir}
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env[hook_base.ROUTE_ROWS_ENV] = self.rows
        argv = [sys.executable, "-c", code, trg.REPORT_GUARD] if code else [sys.executable, trg.REPORT_GUARD]
        run = subprocess.run(argv, input=json.dumps(hook), capture_output=True, text=True, timeout=timeout,
                             env=hook_base.surface_env(env, "local"))
        self.assertEqual(run.returncode, 0, "the Stop hook exited non-zero: " + run.stderr[-300:])
        self.assertNotIn("Traceback", run.stderr, "the Stop hook crashed: " + run.stderr[-300:])
        return run

    # ---- red cases: each fails on code that does not yet read its line. One case per method, so the red count is clean.

    def test_cc_red_notice_is_no_try_for_an_unlanded_claim(self):
        # Catches: a connect-failure notice and a failed grep read as tries of the PR, so the line
        # that says the PR cannot be opened passed. The turn never tried that act: the no-try variant.
        line = "I could not open the PR; open it from your computer."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         *failed_bash("grep -r pulls ci/", "tu_g"), trg.assistant_text(line)])
        self.assert_remedy_names_no_act(self.assert_blocked_for(out, NO_TRY, line))

    def test_cc_red_failed_try_that_names_no_check(self):
        # Catches: a failed try the line does not name read as a claim the check lets through. The try is seen (the
        # variant is names-no-check, not no-try); the line names nothing to check it against.
        line = "I can't open the PR."
        out = self.stop([trg.human("open a PR"), *failed_pr_create(), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_merge_after_a_pushed_commit_has_no_try(self):
        # Catches: a landed turn (a commit and a push) read as a try of every later act. The merge was never tried.
        line = "Unable to merge the PR."
        out = self.stop([trg.human("commit, push and merge"), *ok_bash("git commit -m x", "tu_c"),
                         *ok_bash("git push origin HEAD", "tu_p"), landed_reply(line)])
        self.assert_remedy_names_no_act(self.assert_blocked_for(out, NO_TRY, line))

    def test_cc_red_no_way_to_push_from_the_cloud_has_no_try(self):
        # Catches: the no-way-to phrase missed, or "the cloud" read as not first person.
        line = "There is no way to push from the cloud."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_remedy_names_no_act(self.assert_blocked_for(out, NO_TRY, line))

    def test_cc_red_failed_try_of_another_act_does_not_back_the_claim(self):
        # Catches: a failed push read as a try of opening the PR. A try backs only a claim about its own act.
        line = "I could not open the PR: `git push` failed."
        out = self.stop([trg.human("open a PR"), *failed_bash("git push origin HEAD", "tu_p"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_dead_route_cite_is_no_cite(self):
        # Catches: a route cite that names no row of the rows file read as a cite. Route verdict "dead" is not "ok".
        line = "I cannot open the PR (route r-missing)."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)], rows=[ROW_REFUSED])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pass_other_act_with_no_failure_is_no_claim(self):
        # The act table decides (decision guard-that-cries-wolf-is-spent). A rebase is outside the table, so the line is no
        # claim whether or not a call failed. The call here succeeded, and the line passes.
        line = "I cannot rebase the branch."
        out = self.stop([trg.human("rebase the branch"), *ok_bash("git rebase origin/main", "tu_r"),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a non-table act with a call that succeeded")

    def test_cc_red_lone_quote_does_not_hide_the_claim(self):
        # Catches: a naive quote pattern that pairs the opening quote of 'Cause with the apostrophe in it's, which
        # would blank the claim between them. The apostrophe in it's follows a letter, so no quoted span closes on it.
        line = "'Cause I cannot open the PR, and then it's over."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_comment_openers_in_code_spans_do_not_hide_the_claim(self):
        # Catches: a code span holding a comment opener (// /* #) read as a comment, so the rest of the line is cut.
        line = "The `//`, `/*` and `#` spans are fine; I cannot open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_claim_after_a_multi_line_fence_counts(self):
        # Catches: a fence that a lone backtick inside it (a multi-line template literal) fails to close, which would
        # hide the claim after it.
        line = "I cannot open the PR."
        out = self.stop([trg.human("open a PR"),
                         trg.assistant_text("```\nconst t = `\nprint('x')\n`;\n```\n" + line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_only_the_unbacked_line_is_listed(self):
        # Catches: a reply with one backed claim and one unbacked claim listed as a whole, or the backed line listed.
        backed = "I can't open the PR: `mcp__github__create_pull_request` returned 422."
        unbacked = "I cannot push from here."
        out = self.stop([trg.human("open a PR and push"), *failed_pr_create(),
                         landed_reply(backed + "\n" + unbacked)])
        reason = self.assert_blocked_for(out, NO_TRY, unbacked)
        self.assertNotIn(backed, reason, "a backed line is listed: %s" % reason)

    def test_cc_red_first_person_twin_of_a_third_party_line_blocks(self):
        # The twin of the third-party cases below: the same claim in the first person, with the same empty turn. The
        # subject is the only difference, so those cases pass for the subject and not by accident.
        line = "I can't open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_first_person_twin_of_a_clause_line_blocks(self):
        # The twin of the clause cases below: the same claim with no if, until or telling clause around it.
        line = "I can't merge the PR."
        out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_try_before_the_last_human_message_does_not_count(self):
        # Catches: a try of an earlier turn backing a claim of this one. The window is the turn after the last human
        # message.
        line = "I can't open the PR: `mcp__github__create_pull_request` returned 422."
        out = self.stop([trg.human("open a PR"), *failed_pr_create(), trg.assistant_text("Opened nothing."),
                         trg.human("try again"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    # ---- green: the twins of the reds, and the cites. Each passes for its named reason, with no confounder.

    def test_cc_green_failed_try_with_its_check_named_passes(self):
        # The twin of test_cc_red_failed_try_that_names_no_check: the same records, the line names the tool and its error.
        line = "I can't open the PR: `mcp__github__create_pull_request` returned 422."
        self.assert_passes(self.stop([trg.human("open a PR"), *failed_pr_create(), landed_reply(line)]),
                           "a failed try whose check the line names")

    def test_cc_green_failed_gh_pr_create_names_its_check_passes(self):
        line = "I cannot open the PR: `gh pr create` failed."
        out = self.stop([trg.human("open a PR"), *failed_bash("cd x && gh pr create --title t", "tu_g"),
                         landed_reply(line)])
        self.assert_passes(out, "a failed gh pr create, named")

    def test_cc_green_curl_on_the_pulls_route_with_a_403_passes(self):
        # The text carries the failure as an exit code with no error flag, which counts; the HTTP 403 names the check.
        line = "I cannot open the PR: `curl` returned HTTP 403."
        out = self.stop([trg.human("open a PR"),
                         *failed_bash("curl -s -X POST https://api.github.com/repos/o/r/pulls -d @body.json",
                                      "tu_c", error=False),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a curl to the pulls route, named with its 403")

    def test_cc_green_other_act_with_a_failure_and_its_check_passes(self):
        # The act table decides (decision guard-that-cries-wolf-is-spent). A rebase is outside it, so the line passes with
        # or without a failure. The two failure forms still pass; a failure is not what clears the line.
        line = "I cannot rebase the branch: `git rebase` returned exit code 1."
        for label, error in (("error flag", True), ("exit text only", False)):
            with self.subTest(failure=label):
                out = self.stop([trg.human("rebase the branch"),
                                 *failed_bash("git rebase origin/main", "tu_r", error=error),
                                 trg.assistant_text(line)])
                self.assert_passes(out, "a failed rebase, named (%s)" % label)

    def test_cc_green_failed_try_of_each_route_passes(self):
        # The merge, push and push-files routes of the table. Each call lands, so each reply carries the good report.
        cases = (
            ([*failed_bash("gh pr merge 5", "tu_m")], "I cannot merge the PR: `gh pr merge` failed."),
            ([*failed_bash("git push origin HEAD", "tu_p")], "I cannot push: `git push` failed."),
            ([use("mcp__github__push_files", {"branch": "b"}, "tu_f"), done("tu_f", "HTTP 403 Forbidden", error=True)],
             "I cannot push: `mcp__github__push_files` returned 403."),
        )
        for records, line in cases:
            with self.subTest(line=line):
                out = self.stop([trg.human("push and merge"), *records, landed_reply(line)])
                self.assert_passes(out, "a failed route, named: %s" % line)

    def test_cc_green_agent_result_relaying_a_403_passes(self):
        # Catches: a try an agent made, reported in its result text, read as no try because it is not this session's
        # own call. The spawn names no agent type, and the turn lands on nothing, so only the relay can back the line.
        spawn = use("Agent", {"description": "open the PR", "prompt": "open the PR and report the result"}, "tu_a")
        relay = done("tu_a", "mcp__github__create_pull_request returned HTTP 403 Forbidden")
        line = "I cannot open the PR: `mcp__github__create_pull_request` returned HTTP 403."
        out = self.stop([trg.human("open a PR"), spawn, relay, trg.assistant_text(line)])
        self.assert_passes(out, "an agent's relayed 403")

    def test_cc_green_why_yours_route_cite_is_the_hand_off_guards(self):
        # Pins the skip. The line has a route cite and no check word, so the new check would refuse it as naming no
        # check. It passes only because a Why yours line is the hand-off guard's, which the cite satisfies.
        why = "Why yours: I cannot open the PR (route %s)." % REFUSED_ROW_ID
        out = self.stop([trg.human("open a PR"),
                         trg.assistant_text(input_report("Push the branch from your computer.", why))],
                        rows=[ROW_REFUSED])
        self.assert_passes(out, "a Why yours line with a route cite")

    def test_cc_green_route_cite_on_a_plain_line_passes(self):
        # A line that is not Why yours: its cite (a refused row) backs it, and "refused" names the check.
        line = "I cannot open the PR, since the route was refused (route %s)." % REFUSED_ROW_ID
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)], rows=[ROW_REFUSED])
        self.assert_passes(out, "a plain line with a refused route cite")

    def test_cc_green_measured_cite_on_a_plain_line_passes(self):
        line = "I cannot open the PR (measured 2026-11-06, the route returned 403)."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_passes(out, "a dated measured cite")

    def test_cc_green_refused_tool_named_in_backticks_passes(self):
        # The session's classifier refused the tool. The line names it in backticks, so the refusal backs the claim.
        line = "I cannot open the PR: `%s` was refused this session." % OPEN_PR
        text = input_report("%s was refused this session, so the PR is yours to open." % OPEN_PR)
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line + "\n\n" + text)], refused=[OPEN_PR])
        self.assert_passes(out, "a claim that names a refused tool")

    # ---- must pass: lines the check reads as no claim. Each turn holds no failed try, so only the skip can clear them.

    def test_cc_pass_cannot_be_undone(self):
        # Catches: "cannot be" read as a claim that the act cannot be done.
        out = self.stop([trg.human("push it"), trg.assistant_text("The push cannot be undone.")])
        self.assert_passes(out, "cannot be undone")

    def test_cc_pass_a_claim_in_code_or_quotes_is_not_read(self):
        forms = (
            "Quote it as `I cannot open the PR`.",
            "```\nI cannot open the PR.\nI can't push from here.\n```\nThe fence above is a quote.",
            'Their note says "I cannot open the PR."',
        )
        for text in forms:
            with self.subTest(form=text[:30]):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(text)])
                self.assert_passes(out, "a claim held in code or quotes: %r" % text[:40])

    def test_cc_pass_quoted_rule_text_is_not_read(self):
        out = self.stop([trg.human("open a PR"),
                         trg.assistant_text('The rule reads "I cannot open the PR" and nothing more.')])
        self.assert_passes(out, "quoted rule text")

    def test_cc_pass_a_third_party_subject_is_not_read(self):
        lines = ("The lane cannot push from here.", "The guard can't see the box.",
                 "The builder can't open the PR.", "They cannot merge the PR.",
                 "You cannot push from here.", "It can't open the PR.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a third-party subject: %r" % line)

    def test_cc_pass_a_clause_that_is_no_claim_is_not_read(self):
        # The clause before the phrase holds if, unless, whether or would; the clause after holds until, before, without,
        # or a verb of telling or waiting. Each makes the line a condition, a dependency or a statement of doubt.
        lines = ("If I cannot push from here, I will say so.", "I would not push if I cannot.",
                 "Unless I cannot push, I will stop.", "Whether I can't open the PR is unclear yet.",
                 "I can't merge until CI is green.",
                 "I cannot push before CI ends.", "I can't open the PR without your word.",
                 "I can't tell whether the push went through.", "I cannot guarantee the merge.",
                 "I cannot promise the PR merges.", "I can't wait to push.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a clause that is no claim: %r" % line)

    def test_cc_pass_a_question_or_a_named_rule_is_not_read(self):
        # The question is a prose "?" line, so it runs the past-ruling relay (the model stub answers allow). A line
        # that names a rule is judged as the rule's text, not as the session's claim.
        for line in ("Can I not push from here?", "Could I not open the PR?",
                     "I cannot merge to main (rule git-main-only-by-pr)."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a question or a named rule: %r" % line)

    def test_cc_pass_a_rewrite_under_stop_hook_active_is_not_refused_again(self):
        # Catches: the check refusing the rewrite that follows its own block. Under stop_hook_active only the rewrite
        # checks run, so the claim the first reply made is not refused a second time.
        out = self.stop([trg.human("open a PR"), trg.assistant_text("I cannot open the PR.")], active=True)
        self.assert_passes(out, "the rewrite of a refused reply")

    def test_cc_pass_with_no_human_message_the_check_does_not_run(self):
        out = self.stop([trg.assistant_text("I cannot open the PR.")])
        self.assert_passes(out, "a transcript with no human message")

    def test_cc_control_incident_reply_with_no_claim_passes(self):
        # A turn with a connect-failure notice and a reply that claims nothing. The check stays quiet.
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         *failed_bash("grep -r pulls ci/", "tu_g"),
                         trg.assistant_text("Opening the PR from the MCP route next.")])
        self.assert_passes(out, "the incident turn with a reply that claims nothing")

    # ---- probe lines: each is a bypass of the check or a false alarm. A red fails on the line the check misreads. The
    # green controls keep a line the check must still leave alone.

    def test_cc_red_other_act_is_backed_only_by_a_try_sharing_a_word(self):
        # The act table decides (decision guard-that-cries-wolf-is-spent): "reach GitHub" is the github-reach row, so only a
        # failed GitHub route backs it. The failed grep is no GitHub route, and the notice is no try, so the claim still has
        # no try. The routes that do back it are in the github-reach cases below.
        line = "I can't reach GitHub from here; the MCP server failed to connect."
        out = self.stop([trg.human("reach GitHub"), notice("github: failed to connect"),
                         *failed_bash("grep -r pulls ci/", "tu_g"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_claim_in_a_code_span_is_no_try_for_an_unrelated_failure(self):
        # Catches: code spans blanked before the act is read, so "use ... here" reads as an act of no words, and any
        # failed call backs it. The failed grep shares no word with the tool the span names.
        line = "I can't use `mcp__github__create_pull_request` here; grep returned 1."
        out = self.stop([trg.human("open a PR"), *failed_bash("grep -r pulls ci/", "tu_g"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_claim_of_only_a_code_span_is_no_try(self):
        # Catches: "I can't `gh pr create`." passing because the blanked span leaves no word after the phrase.
        line = "I can't `gh pr create`."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_successful_call_with_refused_in_its_output_is_no_try(self):
        # Catches: a successful call whose output holds the word refused counted as a failed try. A failure is an error
        # flag or an exit code above zero. A status counts only in an error result, so an HTTP 4xx or 5xx in an ok
        # result is no failure. A loose word in the output is none of these.
        line = "I could not open the PR: `gh pr create` failed."
        out = self.stop([trg.human("open a PR"), use("Bash", {"command": "gh pr create --title t"}, "tu_g"),
                         done("tu_g", "3 refused connections in the log; nothing failed."), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_cannot_in_a_hyphenated_name_is_no_claim(self):
        # Catches: "cannot" inside a branch name read as a claim. The phrase ends at a word boundary, not at a hyphen.
        out = self.stop([trg.human("check the branch"),
                         trg.assistant_text("Branch cannot-claim-needs-tries is ready.")])
        self.assert_passes(out, "a branch name that holds cannot")

    def test_cc_red_a_comma_does_not_end_a_would_clause(self):
        # Catches: "would" read across a comma, so a claim after the comma passes as a conditional.
        line = "I would open it, but I can't push."
        out = self.stop([trg.human("push it"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_comma_does_not_end_an_if_clause(self):
        # Catches: "If" read across a comma, so a claim after the comma passes as a condition.
        line = "If the tool fails, I can't open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_comma_does_not_end_a_no_clause(self):
        # Catches: "No," read across a comma, so a claim after it passes as a negated one.
        line = "No, I can't open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_comma_does_not_end_a_not_clause(self):
        # Catches: "did not" read across a comma, so a claim after it passes as a negated one.
        line = "The MCP server did not connect, I could not open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_wasnt_able_to_is_a_claim(self):
        # Catches: "wasn't able to" missing from the phrase list, so the line reads as no claim at all.
        line = "I wasn't able to open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_wont_be_able_to_is_a_claim(self):
        # Catches: "won't be able to" missing from the phrase list.
        line = "I won't be able to push from here."
        out = self.stop([trg.human("push it"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_we_werent_able_to_is_a_claim(self):
        # Catches: "weren't able to" missing from the n't phrases, so the line reads as no claim.
        line = "We weren't able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_we_arent_able_to_is_a_claim(self):
        # Catches: "aren't able to" missing from the n't phrases, so the line reads as no claim.
        line = "We aren't able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_we_arent_able_to_with_a_curly_apostrophe_is_a_claim(self):
        # Catches: the curly apostrophe missing from "aren't", so a straight-quote-only fix passes the other reds.
        line = "We aren’t able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_this_session_isnt_able_to_is_a_claim(self):
        # Catches: "isn't" missing from the be-form n't phrases, so "This session isn't able to" reads as no claim.
        line = "This session isn't able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_we_arent_going_to_be_able_to_is_a_claim(self):
        # Catches: the n't form of "not going to be able to" missing. The listed phrase has no be-form before "not".
        line = "We aren't going to be able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_this_session_isnt_allowed_to_is_a_claim(self):
        # Catches: "isn't allowed to" missing. The record lists "not allowed to", and its n't form counts.
        line = "This session isn't allowed to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_we_arent_allowed_to_is_a_claim(self):
        # Catches: "aren't allowed to" missing, the present plural of the listed "not allowed to".
        line = "We aren't allowed to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_we_arent_allowed_to_with_a_curly_apostrophe_is_a_claim(self):
        # Catches: the curly apostrophe missing from "aren't allowed to", so a straight-quote-only fix passes the other reds.
        line = "We aren’t allowed to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_we_werent_allowed_to_is_a_claim(self):
        # Catches: "weren't allowed to" missing, the past plural of the listed "not allowed to".
        line = "We weren't allowed to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_i_wasnt_allowed_to_is_a_claim(self):
        # Catches: "wasn't allowed to" missing, the singular past of the listed "not allowed to".
        line = "I wasn't allowed to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_this_session_isnt_permitted_to_is_a_claim(self):
        # Catches: "isn't permitted to" missing. The record lists "not permitted to", and its n't form counts.
        line = "This session isn't permitted to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_we_arent_permitted_to_is_a_claim(self):
        # Catches: "aren't permitted to" missing, the present plural of the listed "not permitted to".
        line = "We aren't permitted to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_we_werent_permitted_to_is_a_claim(self):
        # Catches: "weren't permitted to" missing, the past plural of the listed "not permitted to".
        line = "We weren't permitted to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_this_session_isnt_going_to_be_able_to_is_a_claim(self):
        # Catches: "isn't going to be able to" missing. The listed "not going to be able to" has its n't form.
        line = "This session isn't going to be able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_i_wasnt_going_to_be_able_to_is_a_claim(self):
        # Catches: "wasn't going to be able to" missing, the singular past of the listed "not going to be able to".
        line = "I wasn't going to be able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_nt_we_werent_going_to_be_able_to_is_a_claim(self):
        # Catches: "weren't going to be able to" missing, the past plural of the listed "not going to be able to".
        line = "We weren't going to be able to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_be_n_t_able_to_forms_pass_after_a_failed_merge(self):
        # Control: each new form passes after a failed `gh pr merge 12` that the line names as its check.
        # Each form has its own run, so one form's block cannot hide another's pass.
        for line in ("We weren't able to merge PR 12: `gh pr merge 12` exited 1.",
                     "We aren't able to merge PR 12: `gh pr merge 12` exited 1.",
                     "We aren’t able to merge PR 12: `gh pr merge 12` exited 1.",
                     "This session isn't able to merge PR 12: `gh pr merge 12` exited 1.",
                     "We aren't going to be able to merge PR 12: `gh pr merge 12` exited 1.",
                     "This session isn't going to be able to merge PR 12: `gh pr merge 12` exited 1.",
                     "We weren't going to be able to merge PR 12: `gh pr merge 12` exited 1.",
                     "We weren't allowed to merge PR 12: `gh pr merge 12` exited 1.",
                     "We aren't permitted to merge PR 12: `gh pr merge 12` exited 1.",
                     "We aren’t allowed to merge PR 12: `gh pr merge 12` exited 1."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
                self.assert_passes(out, "a failed gh pr merge 12, named as its check, with the form: %r" % line)

    def test_cc_red_no_way_i_can_is_a_claim(self):
        # Catches: "no way I can" missing from the phrase list. Only "no way to" is in it.
        line = "No way I can open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_be_merged_clause_is_a_claim(self):
        # Catches: "be" skipped before any word, so "can't be merged" passes. The skip is for be undone, reverted,
        # reversed, sure and certain only.
        line = "That PR can't be merged from here."
        out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pass_a_be_sure_clause_is_no_claim(self):
        # The comma-free pass the skip keeps: "be sure" and "be reverted" are a doubt and a reversal, not a claim.
        for line in ("I can't be sure the push went through.", "The push can't be reverted."):
            with self.subTest(line=line):
                out = self.stop([trg.human("push it"), trg.assistant_text(line)])
                self.assert_passes(out, "a doubt or a reversal, not a claim: %r" % line)

    def test_cc_red_a_question_at_the_line_end_does_not_hide_a_claim(self):
        # Catches: a whole line skipped for ending in "?", so a claim sentence before the question passes.
        out = self.stop([trg.human("open a PR"), trg.assistant_text("I can't open the PR. Want me to try again?")])
        self.assert_blocked_for(out, NO_TRY, "I can't open the PR.")

    def test_cc_red_a_rule_clause_with_an_id_does_not_hide_a_claim(self):
        # Catches: a whole line skipped for naming a hyphenated rule id, so a claim in another clause of it passes.
        out = self.stop([trg.human("open a PR"), trg.assistant_text(
            "The rule git-main-only-by-pr says merges need CI; I can't open the PR.")])
        self.assert_blocked_for(out, NO_TRY, "I can't open the PR.")

    def test_cc_red_an_unvetted_mid_line_does_not_hide_a_claim(self):
        # Catches: the text after a mid-line "Unvetted:" cut off, so a claim after it passes. Only a line that starts
        # with the marker is the guard's own remedy line.
        out = self.stop([trg.human("open a PR"), trg.assistant_text(
            "Ask the owner about this. Unvetted: none. I can't open the PR.")])
        self.assert_blocked_for(out, NO_TRY, "I can't open the PR.")

    def test_cc_pass_an_unvetted_line_start_is_the_guards_form(self):
        # The guard's own Unvetted line, which starts with the marker, is left alone.
        out = self.stop([trg.human("open a PR"),
                         trg.assistant_text("Unvetted: the ruling is open; I cannot open the PR.")])
        self.assert_passes(out, "the guard's own Unvetted line")

    def test_cc_red_a_later_phrase_in_an_if_clause_is_judged(self):
        # Catches: a later phrase read under an "if" that sits before the first phrase in the same clause, so the later
        # claim, which its own words do not condition, passes.
        line = "If the tool fails I can't push and I could not open the PR."
        out = self.stop([trg.human("push and open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_later_success_cancels_an_earlier_failure(self):
        # Catches: a failed create backing a claim made after a later create of the same route succeeded.
        line = "I can't open the PR: `mcp__github__create_pull_request` returned 422."
        out = self.stop([trg.human("open a PR"), *failed_pr_create("tu_1"),
                         use(OPEN_PR, {"title": "t", "head": "b", "base": "main"}, "tu_2"),
                         done("tu_2", "created #7"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_the_remedy_names_the_route_and_measured_cites(self):
        # Catches: a remedy that names the try and the check but not the cite forms a line may carry, so a reader cannot
        # tell that a route cite or a dated measurement clears the line.
        line = "I could not open the PR; open it from your computer."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         *failed_bash("grep -r pulls ci/", "tu_g"), trg.assistant_text(line)])
        reason = self.assert_blocked_for(out, NO_TRY, line)
        self.assertIn("Remedy:", reason)
        self.assertIn("Lines:", reason)
        remedy = reason[reason.index("Remedy:"):reason.index("Lines:")]
        self.assertIn("(route", remedy, "the remedy names no route cite: %s" % remedy)
        self.assertIn("(measured", remedy, "the remedy names no measured cite: %s" % remedy)

    # ---- the act table (decision guard-that-cries-wolf-is-spent). A claim counts only when its act is a table act: pr-open,
    # pr-merge, push, pr-edit or github-reach. A claim of any other act passes. Each probe line is a subTest, so a red
    # names the line.

    def test_cc_red_r1_f1_false_alarms_pass(self):
        # A claim of an act outside the table is no claim. The last line's subject is a third party. None of the lines has a
        # try in its turn, so only the table can clear them.
        lines = ("I couldn't find any callers of that function.", "I can't run the tests here; `pytest` exited 2.",
                 "The read cannot stop the merge.", "I can't open the file in the editor.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("check the callers"), trg.assistant_text(line)])
                self.assert_passes(out, "a round 1 false alarm: %r" % line)

    def test_cc_red_r1_f2_failed_gh_api_backs_a_github_reach_claim(self):
        # A failed gh call is a GitHub route, so it is a try of the github-reach act. The line names the call.
        line = "I can't reach GitHub from here: `gh api` returned 403."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("gh api repos/o/r", "tu_a"),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a failed gh api is a GitHub route try")

    def test_cc_red_r1_f2_failed_ls_remote_backs_a_github_reach_claim(self):
        # git ls-remote is a GitHub route when it reads the remote, so a failed one backs the claim.
        line = "I can't reach GitHub from here: `git ls-remote` failed."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("git ls-remote origin", "tu_l"),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a failed git ls-remote is a GitHub route try")

    def test_cc_red_r1_f2_a_grep_sharing_a_word_backs_no_github_reach_claim(self):
        # A grep whose command holds the word github is no GitHub route, so it backs nothing. The claim names the grep, so
        # the no-try variant is the one that fires.
        line = "I can't reach GitHub from here: `grep -r github ci/` returned 1."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("grep -r github ci/", "tu_g"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_r1_f2_access_the_github_api_needs_a_github_route_try(self):
        # "access the GitHub API" is the github-reach row. The failed grep shares the word github and is no route.
        line = "I can't access the GitHub API from here."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("grep -r github ci/", "tu_g"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r1_f2_reach_github_with_only_a_notice_blocks(self):
        # Control: a connect notice is no try, so the github-reach claim still has none.
        line = "I can't reach GitHub from here."
        out = self.stop([trg.human("reach GitHub"), notice("github: failed to connect"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_r2_a_draft_pr_subject_is_third_party(self):
        # The subject just before the phrase must be first person, or the phrase opens its clause. "A draft PR" is
        # neither, so the line is no claim about this session.
        for line in ("The draft PR cannot be merged yet.", "A draft PR can't be merged here."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge the draft"), trg.assistant_text(line)])
                self.assert_passes(out, "a draft PR as the subject: %r" % line)

    def test_cc_green_r2_first_person_subjects_block(self):
        # Control: the cloud and this session are first person, so the claim blocks.
        for line in ("The cloud cannot open the PR.", "This session can't open the PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r2_a_builder_or_the_session_passes(self):
        # Control: a builder is a third party, and "the session" stays third party (only "this session" is first).
        for line in ("The builder cannot open the PR.", "The session cannot open the PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a third-party subject: %r" % line)

    def test_cc_red_r3_a_later_success_on_another_target_does_not_cancel(self):
        # A later success cancels an earlier failure only for the same act, the same target and the same verb. Merge
        # 13 is another PR, so the failed merge of 12 still backs the claim about 12.
        line = "I cannot merge PR 12: `gh pr merge 12` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m1"),
                         *ok_bash("gh pr merge 13", "tu_m2"), landed_reply(line)])
        self.assert_passes(out, "a success on PR 13 against a failure on PR 12")

    def test_cc_red_r3_a_later_success_with_another_verb_does_not_cancel(self):
        # A comment on PR 12 is the same act as a close of PR 12 (pr-edit), but another verb, so it cancels nothing.
        line = "I cannot close PR 12: `gh pr close 12` failed."
        out = self.stop([trg.human("close PR 12"), *failed_bash("gh pr close 12", "tu_c1"),
                         *ok_bash("gh pr comment 12 --body done", "tu_c2"), landed_reply(line)])
        self.assert_passes(out, "a comment on PR 12 against a failed close of PR 12")

    def test_cc_red_r3_a_dry_run_success_does_not_cancel(self):
        # A call with --dry-run never cancels a failure, so a dry run that succeeded leaves the failed merge standing.
        line = "I cannot merge PR 12: `gh pr merge 12` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m1"),
                         *ok_bash("gh pr merge 12 --dry-run", "tu_m2"), landed_reply(line)])
        self.assert_passes(out, "a dry run that succeeded against a failed merge")

    def test_cc_red_r3_a_failed_dry_run_is_no_try(self):
        # A call with --dry-run never counts as a try either, so a failed dry run backs no claim of the merge.
        line = "I cannot merge PR 12: `gh pr merge 12 --dry-run` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12 --dry-run", "tu_d"),
                         landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r3_a_same_target_and_verb_success_cancels(self):
        # Control: the same act, target and verb, succeeding later, still cancels the failure.
        line = "I cannot merge PR 12: `gh pr merge 12` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m1"),
                         *ok_bash("gh pr merge 12", "tu_m2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    # ---- a reason in the line names the check; a later success makes a past failure no claim

    def test_cc_red_a_reason_in_parentheses_names_the_check_after_a_failed_merge(self):
        # Catches: the check reads only backticks, tool names and error words as naming the check, so a failed merge
        # with its reason in parentheses blocked as naming no check.
        line = "I cannot merge PR 12 (the PR is not mergeable)."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_passes(out, "a failed merge, with its reason in parentheses")

    def test_cc_red_a_reason_after_a_colon_names_the_check_after_a_failed_push(self):
        # Catches: the remote's rejection after the colon read as no check, so a failed push blocked its own claim.
        line = "I couldn't push: the remote rejected the ref."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         landed_reply(line)])
        self.assert_passes(out, "a failed push, with the remote's reason after a colon")

    def test_cc_red_a_werent_reason_after_a_colon_names_the_check_after_a_failed_merge(self):
        # Catches: "weren't" missing from the verbs of a reason, so "the tests weren't green" named no check and blocked a
        # failed merge that its own reason explained. The curly apostrophe reads the same.
        for line in ("I couldn't merge PR 12: the tests weren't green.", "I couldn’t merge PR 12: the tests weren’t green."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
                self.assert_passes(out, "a failed merge, with a weren't reason after the colon: %r" % line)

    def test_cc_green_an_aren_t_reason_after_a_colon_passes_after_a_failed_merge(self):
        # Control: the same failed merge, with aren't in the reason. aren't is a verb of a reason already, so it passes.
        line = "I couldn't merge PR 12: the tests aren't green."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_passes(out, "a failed merge, with an aren't reason after the colon")

    def test_cc_red_a_later_push_success_makes_a_past_failure_no_claim(self):
        # Catches: a push that failed and was then pushed again read as a present claim that the push cannot be done.
        # The later success of the same push makes the failed one a past failure, so the line is no claim.
        line = "I could not push at first; I rebased and pushed."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p1"),
                         *ok_bash("git push origin HEAD", "tu_p2"), landed_reply(line)])
        self.assert_passes(out, "a failed push, a later successful push, and the past failure named")

    def test_cc_red_a_later_merge_success_makes_a_past_failure_no_claim(self):
        # Catches: a merge that failed through the GitHub MCP tool and merged on a retry read as a present claim.
        line = "I couldn't merge PR 12 on the first try; the retry merged it."
        merge = {"owner": "o", "repo": "r", "pullNumber": 12}
        out = self.stop([trg.human("merge PR 12"),
                         use("mcp__github__merge_pull_request", merge, "tu_m1"),
                         done("tu_m1", "Pull request is not mergeable", error=True),
                         use("mcp__github__merge_pull_request", merge, "tu_m2"), done("tu_m2", "merged"),
                         landed_reply(line)])
        self.assert_passes(out, "a failed merge tool call, a later successful retry, and the past failure named")

    def test_cc_green_a_bare_claim_after_a_failed_merge_still_blocks(self):
        # Control: the same failed try, and a claim with no reason. The line names no check, so it blocks.
        line = "I cannot merge PR 12."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_green_a_success_of_another_act_does_not_rescue_a_notice_only_claim(self):
        # Control: a successful push is a success of another act. It does not back a claim that the PR cannot be opened
        # when the only thing the turn holds is a connect-failure notice, so the line still blocks as having no try.
        line = "I could not open the PR."
        out = self.stop([trg.human("open a PR"), notice("github: failed to connect"),
                         *ok_bash("git push origin HEAD", "tu_p"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_past_unable_to_push_recovered_by_a_later_push_is_no_claim(self):
        # Catches: "was unable to" and "was not able to" read as a present claim that the push cannot be done, although a
        # later push of the same target succeeded. A phrase after was or were is a past failure, so the line is no claim.
        for line in ("I was unable to push at first; I rebased and pushed.",
                     "I was not able to push at first; I rebased and pushed."):
            with self.subTest(line=line):
                out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p1"),
                                 *ok_bash("git push origin HEAD", "tu_p2"), landed_reply(line)])
                self.assert_passes(out, "a past failure of a push that a later push recovered")

    def test_cc_green_a_present_unable_to_push_after_a_recovered_push_still_blocks(self):
        # Control: "I am unable to push." is a present claim. The later push cancels the failure, so the line blocks as
        # having no try.
        line = "I am unable to push."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p1"),
                         *ok_bash("git push origin HEAD", "tu_p2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_past_werent_form_recovered_by_a_later_merge_is_no_claim(self):
        # Catches: "weren't" dropped from the past-tense read (CANNOT_PAST_RE), so "We weren't able to merge PR 12 at
        # first" reads as a present claim that the merge cannot be done, although a later merge of the same PR
        # succeeded. Each form runs after a failed `gh pr merge 12` and a later success in the turn.
        for claim in WEREN_T_CLAIMS:
            line = claim + " at first; the retry merged it."
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m1"),
                                 *ok_bash("gh pr merge 12", "tu_m2"), landed_reply(line)])
                self.assert_passes(out, "a past failure of a merge that a later merge recovered: %r" % line)

    def test_cc_green_a_werent_form_without_a_later_merge_still_blocks(self):
        # Control: the same claims after the same failed merge, with no later success and no reason. Each line is read
        # as a claim here, so the pass above comes from the past read and not from a line the check never reads.
        for claim in WEREN_T_CLAIMS:
            line = claim + "."
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
                self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_r4_rule_forms_and_the_cannot_suite_pass(self):
        # A sentence that names a rule or a decision is the rule's text, not the session's claim. "Cannot" directly
        # before a noun used as a modifier (the cannot suite, the cannot cases) is no claim.
        lines = ("Rule: I cannot open the PR here.", "Per the decision, I cannot open the PR.",
                 "Decision: pr-open-needs-grant (I cannot open the PR).", "The cannot suite passes.",
                 "The cannot cases pass.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a rule form or a modifier: %r" % line)

    def test_cc_red_r5_a_cloud_session_after_a_skipped_phrase_blocks(self):
        # Each phrase of a line is judged. The first phrase's subject is a third party. The second names the cloud
        # session, which is first person, so the line blocks on the second.
        line = "The guard can't see the box, and the cloud session cannot open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_r5_the_cloud_session_cannot_open_the_pr_blocks(self):
        # "the cloud session" is first person, so the line is a claim about this session.
        line = "The cloud session cannot open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r5_two_phrases_both_judged_block(self):
        # Control: a third-party first phrase does not clear the line, because the second phrase is a claim.
        line = "The read cannot stop the merge, and I can't open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pin_r7_an_unreadable_refusals_file_fails_open_with_an_unknown_note(self):
        # A refusals file that cannot be read skips the check (fail open), and the Stop run says so on stderr as
        # UNKNOWN. The claim is not refused, and the note is not silent. The path is a directory, so opening it fails.
        path = os.path.join(self.cfg, "state", "refusals", "cannot-sid-1.jsonl")
        os.makedirs(path)
        hook_base.write_route_rows(self.rows, [])
        transcript = trg.write_transcript([trg.human("open a PR"), trg.assistant_text("I cannot open the PR.")],
                                          self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": transcript, "stop_hook_active": False,
                "cwd": self.run_dir, "session_id": "cannot-sid-1"}
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env[hook_base.ROUTE_ROWS_ENV] = self.rows
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=hook_base.surface_env(env, "local"))
        self.assertEqual(run.returncode, 0, "the Stop hook exited non-zero: " + run.stderr[-300:])
        self.assertNotIn("Traceback", run.stderr, "the Stop hook crashed: " + run.stderr[-300:])
        self.assertIn("cannot-claim guard: UNKNOWN", run.stderr, "no UNKNOWN note on stderr: %r" % run.stderr[-300:])
        self.assertFalse(run.stdout.strip(), "an unread refusals file refused the claim: %s" % run.stdout)

    # ---- a blocker skips only the acts it blocks, in its own clause; a script named for an act is a try of it

    def test_cc_red_a_blocker_does_not_cross_a_comma_to_skip_another_claim(self):
        # Catches: a because clause read across ", and", so a blocker on CI skipped an open claim that CI does not block. CI
        # blocks a merge; the open claim sits in the clause after the comma and must still be judged.
        line = "I can't merge PR 12 because CI is red, and I could not open the lane PR."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_blocker_for_a_merge_does_not_skip_an_open_claim(self):
        # Catches: CI red, read as a blocker of an open claim. A red check blocks a merge, not an open.
        for line in ("I can't open the PR because CI is red.",
                     "I could not open the PR because the MCP server failed to connect, and CI is red."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_blocker_on_ci_still_skips_a_merge_claim(self):
        # Control: CI red blocks a merge, so a merge claim whose clause carries it is no claim, and it passes.
        line = "I can't merge PR 12 because CI is red."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_passes(out, "a merge claim whose blocker is CI")

    def test_cc_green_a_main_protection_blocker_skips_a_push_claim(self):
        # Control: a protected main blocks a push, so a push to main that the branch rule forbids is no claim, and it passes.
        line = "I can't push to main because main is protected."
        out = self.stop([trg.human("push to main"), trg.assistant_text(line)])
        self.assert_passes(out, "a push claim whose blocker is that main is protected")

    def test_cc_red_a_hyphenated_preposition_word_does_not_hide_the_pr(self):
        # Catches: "in", "per" and "on" read as prepositions inside a hyphenated word, so the PR after it was not reached
        # and the open claim passed as no claim.
        for line in ("I can't open the in-progress PR.", "I can't open the per-lane PR.", "I can't open the on-hold PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_failed_script_named_for_an_act_is_a_try_of_it(self):
        # Catches: a script named for an act read as no try, so its failure backed no claim of that act. An interpreter
        # with a version suffix (python3.12) and a make call with -C dir are read as the script or target they run.
        for command, line in (
                ("scripts/pr-open.sh", "I can't open the PR: `pr-open.sh` returned exit code 1."),
                ("./tools/gh-pr-create.sh --title t", "I cannot open the PR: `gh-pr-create.sh` returned exit code 1."),
                ("python3.12 scripts/push.py", "I couldn't push: `push.py` returned exit code 1."),
                ("make -C dir push", "I couldn't push: `make -C dir push` returned exit code 1.")):
            with self.subTest(command=command):
                out = self.stop([trg.human("push or open the PR"), *failed_bash(command, "tu_s"), landed_reply(line)])
                self.assert_passes(out, "a failed `%s` backs its claim" % command)

    def test_cc_red_a_bare_npm_push_is_no_try_of_push(self):
        # Catches: "npm push" read as a script named push, so its failure backed a push claim. npm has no push command;
        # a run script whose name holds push (npm run push-docs) is still a try.
        line = "I couldn't push: `npm push` returned exit code 1."
        out = self.stop([trg.human("push the docs"), *failed_bash("npm push", "tu_np"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_failed_python_script_names_no_act_and_backs_no_push(self):
        # Control: the script python3.12 x.py names no act, so its failure backs no claim of a push, and the claim blocks.
        line = "I couldn't push: `python3.12 x.py` returned exit code 1."
        out = self.stop([trg.human("push the branch"), *failed_bash("python3.12 x.py", "tu_x"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    # ---- a script try backs its claim only when the line names the script; the CI and joining-noun skips are reverted (coordinator ruling 04:31 CST)

    def assert_blocks(self, out, line):
        """A block by the cannot-claim guard that lists `line`, whatever its variant."""
        self.assertIsNotNone(out, "no block came for %r" % line)
        self.assertEqual(out.get("decision"), "block", "not a block: %s" % out)
        self.assertIn(HEAD, out.get("reason", ""), "the block is not the cannot-claim guard: %s" % out)
        self.assertIn(line, out.get("reason", ""), "the claim line is not listed: %s" % out)

    def test_cc_red_a_script_try_backs_a_claim_only_when_the_line_names_the_script(self):
        # Catches: a failed script whose name holds an act word read as a try of that act, so a line that does not name the
        # script was backed by it. Without the name, the failed script backs no claim.
        for command, code, line in (
                ("echo {} | python3 hooks/guard_merge.py", 2, "I can't merge PR 12: the API refused the merge."),
                ("echo {} | python3 hooks/guard_push_delete.py", 1,
                 "I can't push the branch: the API refused the push.")):
            with self.subTest(command=command):
                out = self.stop([trg.human("act now"), *exit_bash(command, code, "tu_s"), landed_reply(line)])
                self.assert_blocks(out, line)

    def test_cc_green_a_failed_script_named_in_the_line_backs_its_claim(self):
        # Control: a failed script named in the line backs the claim about its act, so the line passes.
        for command, code, line in (
                ("./open-pr.sh", 1, "I could not open the PR: `open-pr.sh` exited 1."),
                ("merge 12", 1, "I couldn't merge PR 12: `merge 12` exited 1.")):
            with self.subTest(command=command):
                out = self.stop([trg.human("act now"), *exit_bash(command, code, "tu_s"), landed_reply(line)])
                self.assert_passes(out, "a failed %s, named in the line" % command)

    def test_cc_red_a_ci_blocker_blocks_a_merge_claim_in_each_phrasing(self):
        # Catches: a CI state read as a merge blocker, so the merge claim beside it passed with no try. Coordinator ruling
        # 04:31 CST, revert of skip widenings: these phrasings name no blocker, so the claim blocks.
        for line in ("I can't merge PR 12 because CI failed.", "I can't merge PR 12 as CI is red.",
                     "CI is red and I can't merge PR 12."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_failing_ci_still_blocks_an_open_claim(self):
        # Control: CI gates a merge only, so an open claim with no try still blocks while CI has failed.
        line = "I can't open the PR because CI failed."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocks(out, line)

    def test_cc_green_a_failed_server_is_no_blocker_for_a_merge_claim(self):
        # Control: a failed server names no blocker, so the merge claim it sits beside still blocks.
        line = "The MCP server failed and I can't merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocks(out, line)

    def test_cc_red_an_object_window_does_not_stop_at_a_joining_noun(self):
        # Catches: "open the CI logs and PR" read with the and ending the object, so the open of the PR went unread. Coordinator
        # ruling 04:31 CST, revert of skip widenings: the and or or stop is reverted, so the PR is the object and the claim blocks.
        line = "I could not open the CI logs and PR."
        out = self.stop([trg.human("open the PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_pr_object_or_a_verb_pair_still_claims(self):
        # Control: an object PR after a modifier, or a verb pair before the object, is still an open or create claim.
        for line in ("I could not open the follow-up PR.", "I can't create and push the PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open the PR"), trg.assistant_text(line)])
                self.assert_blocks(out, line)

    # ---- a failed connection or health check is no blocker; the merge tool names the merge script; the and or or stop of the object window is reverted (coordinator ruling 04:31 CST)

    def test_cc_red_a_failed_connection_is_no_blocker_for_a_merge_claim(self):
        # Catches: "CI failed to connect" and "the checks failed to connect" read as a CI blocker, so the merge claim beside
        # them passed as backed. A failure to connect is an outage, so the claim has no try and blocks.
        for line in ("I can't merge PR 12 because CI failed to connect.",
                     "I can't merge PR 12 because the checks failed to connect."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocks(out, line)

    def test_cc_red_a_failed_health_check_is_no_blocker_for_a_merge_claim(self):
        # Catches: "the MCP health check failed" read as a CI check blocker, so the merge claim it sat beside passed.
        line = "The MCP health check failed and I can't merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocks(out, line)

    def test_cc_red_a_ci_failure_blocks_a_merge_claim(self):
        # Catches: CI failing, or CI red, read as a merge blocker, so the merge claim beside it passed with no try. Coordinator
        # ruling 04:31 CST, revert of skip widenings: a CI state names no blocker here, so the claim blocks.
        for line in ("I can't merge PR 12 because CI failed.", "CI is red and I can't merge PR 12."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_the_merge_tool_names_the_merge_script(self):
        # Catches: "the merge tool" not read as naming the merge script, so a failed merge 12 did not back its claim
        # (the script try backs a claim only when the line names it).
        line = "I couldn't merge PR 12: the merge tool exited 1."
        out = self.stop([trg.human("merge PR 12"), *exit_bash("merge 12", 1, "tu_m"), landed_reply(line)])
        self.assert_passes(out, "a failed merge 12, named in the line as the merge tool")

    def test_cc_green_a_failed_other_script_is_no_merge_tool(self):
        # Control: a failed ./lint.sh is no merge tool, so the same line blocks.
        line = "I couldn't merge PR 12: the merge tool exited 1."
        out = self.stop([trg.human("merge PR 12"), *exit_bash("./lint.sh", 1, "tu_l"), landed_reply(line)])
        self.assert_blocks(out, line)

    def test_cc_red_an_article_before_the_pr_after_and_or_still_claims(self):
        # Catches: an and or or before a bare PR stopping the object window even when the noun after it has an article, so
        # the open or create claim went unread.
        for line in ("I could not create the branch and the PR.", "I could not open the logs or the PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open the PR"), notice("github: failed to connect"), trg.assistant_text(line)])
                self.assert_blocks(out, line)

    def test_cc_red_an_and_joined_noun_before_a_bare_pr_still_claims(self):
        # Catches: "the CI logs and PR" read as joining a bare PR to a noun, so the open passed as no claim. Coordinator ruling
        # 04:31 CST, revert of skip widenings: the and or or stop is reverted, so the open is a claim and blocks.
        line = "I could not open the CI logs and PR."
        out = self.stop([trg.human("open the PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    # ---- an and or or after create or raise does not stop the object window; a failed word before to is an outage; a CI state names no blocker (coordinator ruling 04:31 CST)

    def test_cc_red_a_create_or_raise_claim_with_and_or_or_still_blocks(self):
        # Catches: the and or or stop of the object window applied to open only, so "create the branch and PR" read its PR as
        # outside the claim, and the claim passed with no try.
        for line in ("I could not create the branch and PR.", "I couldn't create a branch and PR.",
                     "I can't create the branch or PR.", "I could not raise the issue and PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open the PR"), notice("github: failed to connect"), trg.assistant_text(line)])
                self.assert_blocks(out, line)

    def test_cc_red_a_failed_word_before_to_is_an_outage(self):
        # Catches: "failed" or "failing" before to read as a CI blocker, so a merge claim beside an outage passed as backed.
        # The lines with with, a colon or a paren also block and stay here. A health-check that failed is an outage too,
        # with a hyphen as with a space.
        for line in ("The health-check failed and I can't merge PR 12.",
                     "I can't merge PR 12 because CI failed: connection refused.",
                     "I can't merge PR 12 because CI failed (connection refused).",
                     "I can't merge PR 12 because CI failed with a connection error.",
                     "I can't merge PR 12 because the checks failed to fetch.",
                     "The connectivity check failed and I can't merge PR 12.",
                     "I can't merge PR 12 because CI is failing to start."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocks(out, line)

    def test_cc_red_a_ci_that_has_failed_blocks_a_merge_claim(self):
        # Catches: "CI has failed" skipped as a merge blocker, so the merge claim beside it passed with no try. Coordinator
        # ruling 04:31 CST, revert of skip widenings: the has-failed tail names no blocker here, so the claim blocks.
        line = "I can't merge PR 12 because CI has failed."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_connection_or_network_check_failure_is_an_outage_for_a_merge_claim(self):
        # Catches: "connection check" and "network check" read as a CI check blocker, so a merge claim beside an outage with
        # only a connect notice passed as backed. Both checks are outages, so the claim has no try and blocks.
        for line in ("I can't merge PR 12 because the MCP connection check failed.",
                     "I can't merge PR 12 because the network check failed."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), notice("github: failed to connect"), trg.assistant_text(line)])
                self.assert_blocks(out, line)

    # ---- an adverb or emphasis before the act is still the act; a Why yours line is judged as a claim; a failed try backs a claim only in its own turn, for its own act, with a status and the same target

    def test_cc_red_an_adverb_or_emphasis_before_the_act_still_claims(self):
        # Catches: an adverb such as currently or yet, or emphasis around the verb or the object, read past the act, so the
        # claim had no act and passed as no claim.
        for prompt, line in (("merge PR 12", "I currently cannot merge PR 12."),
                             ("open the PRs", "I am currently unable to open PRs."),
                             ("push the branch", "I am not yet able to push."),
                             ("merge PR 12", "I cannot **merge** PR 12."),
                             ("push the branch", "I can't `push` the branch.")):
            with self.subTest(line=line):
                out = self.stop([trg.human(prompt), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_an_ly_adverb_before_i_tried_names_no_check(self):
        # Catches: the writer adverbs read from the twelve listed words only, so "I genuinely tried" let the bare check word
        # tried name a check. Any -ly adverb between I and tried is the writer's own, so tried names no call.
        line = "I genuinely tried, and I cannot push."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_green_a_listed_adverb_before_i_tried_names_no_check(self):
        # Control: actually is a listed adverb, so the writer reads as the subject and the line blocks for naming no check.
        line = "I actually tried, and I cannot push."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_why_yours_line_with_a_capability_phrase_is_judged_as_a_claim(self):
        # Catches: a Why yours line skipped by the cannot-claim check, so "I am not able to push from here" passed with no try.
        line = "Why yours: I am not able to push from here, so you must run it."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_failed_try_before_a_peer_message_does_not_back_a_claim(self):
        # Catches: a failed try from an earlier peer-driven turn read as this turn's try, so the claim beside it passed.
        line = "I cannot merge PR 12; `gh pr merge` exited 1."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), trg.peer_msg("status?"),
                         landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_failed_try_before_a_human_message_does_not_back_a_claim(self):
        # Control: a failed try in an earlier turn, with a human message between it and the reply, backs no claim.
        line = "I cannot merge PR 12; `gh pr merge` exited 1."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), trg.human("try again"),
                         landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_refused_tool_named_in_a_line_backs_only_its_own_act(self):
        # Catches: a refused tool named in the line read as backing every act, so a push claim was backed by a refused GitHub
        # call that is no push.
        line = "I can't push the branch, since `mcp__github__get_me` was refused."
        reply = line + "\n\n" + input_report("allow `mcp__github__get_me`?")
        out = self.stop([trg.human("push the branch"), trg.assistant_text(reply)], refused=("mcp__github__get_me",))
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_refused_tool_named_in_a_line_backs_its_own_act(self):
        # Control: a refused GitHub call backs a reach-GitHub claim that names it, so the line passes.
        line = "I can't reach GitHub from here, since `mcp__github__get_me` was refused."
        reply = line + "\n\n" + input_report("allow `mcp__github__get_me`?")
        out = self.stop([trg.human("reach GitHub"), trg.assistant_text(reply)], refused=("mcp__github__get_me",))
        self.assertFalse(out and out.get("decision") == "block",
                         "a reach-GitHub claim backed by its own refused call was blocked: %s" % out)

    def test_cc_red_a_number_that_is_no_status_names_no_check(self):
        # Catches: "450" in "the 450-line diff" read as an HTTP 4xx, so a line whose only check word was a diff size named one.
        line = "I cannot merge PR 12, the 450-line diff."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_green_a_returned_http_status_names_the_check(self):
        # Control: an HTTP status after returned is a status, so the line names its check and passes.
        line = "I cannot merge PR 12; `gh pr merge` returned HTTP 405."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_passes(out, "a claim whose status is a returned HTTP 405")

    def test_cc_red_a_later_merge_of_the_same_pr_with_its_flags_moved_cancels_the_failure(self):
        # Catches: the cancel key taking the first token after the verb, so "gh pr merge --squash 12" and "gh pr merge 12
        # --squash" had different keys, and the later success did not cancel the earlier failure of the same PR.
        line = "I cannot merge PR 12; `gh pr merge` exited 1."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge --squash 12", "tu_1"),
                         *ok_bash("gh pr merge 12 --squash", "tu_2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_later_merge_of_another_pr_does_not_cancel_the_failure(self):
        # Control: a later success of PR 13 is another target, so the failed try of PR 12 still backs its claim.
        line = "I cannot merge PR 12; `gh pr merge` exited 1."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_1"),
                         *ok_bash("gh pr merge 13", "tu_2"), landed_reply(line)])
        self.assert_passes(out, "a failed merge of PR 12, not cancelled by a merge of PR 13")

    def test_cc_red_a_url_of_another_repo_does_not_cancel_a_repo_less_failure(self):
        # Catches: a PR URL keyed by its number alone, so a merge of o/x PR 12 cancelled a failed merge of PR 12 whose repo
        # the call never named. The failure stands, so the line that says it could not merge names no check and blocks.
        line = "I could not merge PR 12 at first."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_1"),
                         *ok_bash("gh pr merge https://github.com/o/x/pull/12", "tu_2"), landed_reply(line)])
        self.assertIsNotNone(out, "the merge of o/x PR 12 cancelled the failed merge of PR 12 with no repo named")
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_same_repo_url_cancels_a_failure_made_with_the_repo_flag(self):
        # Catches: a PR URL's repo dropped from its key, so the merge of o/x PR 12 by URL did not cancel the failed merge of
        # PR 12 made with --repo o/x. The same repo and number cancel, so the past failure is no claim.
        line = "I could not merge PR 12 at first."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12 --repo o/x", "tu_1"),
                         *ok_bash("gh pr merge https://github.com/o/x/pull/12", "tu_2"), landed_reply(line)])
        self.assert_passes(out, "the URL merge of o/x PR 12 did not cancel the failed merge made with --repo o/x")

    def test_cc_green_a_same_url_retry_cancels_a_failed_url_merge(self):
        # Control: a merge by URL that fails, then a retry of the same URL. Both keys name the same repo and number, so the
        # retry cancels the failure, and the line that says it could not merge at first passes.
        line = "I could not merge PR 12 at first."
        url = "https://github.com/o/x/pull/12"
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge " + url, "tu_1"),
                         *ok_bash("gh pr merge " + url, "tu_2"), landed_reply(line)])
        self.assert_passes(out, "a failed merge by URL, then a successful retry of the same URL")

    # ---- a reason after a failed try names its check, whatever the mark that sets it off, and a check in one sentence backs the next

    def test_cc_red_a_reason_after_a_failed_push_names_the_check(self):
        # Catches: a reason set off by a comma, a semicolon or a dash read as naming no check, so a push that failed for a
        # stated reason blocked as naming no check.
        for line in ("I could not push, the branch is protected.", "I could not push; the branch is protected.",
                     "I could not push — the branch is protected."):
            with self.subTest(line=line):
                out = self.stop([trg.human("push the branch"),
                                 *failed_bash("git push origin HEAD:cannot-claim-follow-up-3", "tu_p"), landed_reply(line)])
                self.assert_passes(out, "a push claim whose failed try is named by a reason")

    def test_cc_red_a_check_in_the_prior_sentence_backs_the_claim_after_it(self):
        # Catches: a check named in the sentence before a claim read as not naming that claim's check, so the claim after a
        # returned 403 blocked as naming no check.
        reply = "`gh pr create` returned 403. I cannot open the PR from here."
        out = self.stop([trg.human("open the PR"),
                         use("Bash", {"command": "gh pr create --title t"}, "tu_c"),
                         done("tu_c", "HTTP 403 Forbidden", error=True), landed_reply(reply)])
        self.assert_passes(out, "a claim after a sentence that names a returned 403")

    def test_cc_green_a_reason_with_no_failed_try_still_blocks(self):
        # Control: with no failed try, a reason after a comma does not name a check, so the claim blocks as no try.
        line = "I could not push, the branch is protected."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    # ---- a claim after a bold report label. "**Input Needed** Could not open the PR" is a hand-off form.
    # The label is no subject: the clause after it opens, so the phrase has an empty subject and is a claim.

    def test_cc_red_a_claim_after_a_bold_input_needed_label_has_no_try(self):
        # Catches: the bold label read as the phrase's subject, so the line passed as no claim. The only evidence is a
        # connect notice, which is no try.
        line = "**Input Needed** Could not open the PR."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_claim_in_an_input_needed_report_line_has_no_try(self):
        # The same claim as the Input Needed line of a report, the hand-off form the check must read.
        line = "**Input Needed** Could not open the PR."
        report = "\n".join(["> **Done** BUILT abc123", "> **Deviations** none", "> " + line, "> **Next** wait"])
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(report)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_claim_in_a_next_report_line_has_no_try(self):
        # The same claim under Next: the label is the phrase's clause opener under every label, not Input Needed only.
        line = "**Next** Could not open the PR."
        report = "\n".join(["> **Done** BUILT abc123", "> **Deviations** none", "> **Input Needed** none", "> " + line])
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(report)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_third_party_after_a_bold_label_passes(self):
        # Control: the label opens the clause, and the subject after it is still judged. A builder is third party.
        line = "**Input Needed** The builder could not open the PR."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a third-party subject after a bold label")

    def opened_by_stop(self, reply):
        """(stdout, paths the Stop process opened, the refusals path, the transcript path) for one reply, with a refusals
        file and the route rows in place. The refusals file is written again for each run: a run that settles it removes
        it."""
        refusals = os.path.join(self.cfg, "state", "refusals", "cannot-sid-1.jsonl")
        os.makedirs(os.path.dirname(refusals), exist_ok=True)
        with open(refusals, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": "2026-11-06T10:00:00-06:00", "tool_name": OPEN_PR,
                                     "reason": "refused"}) + "\n")
        hook_base.write_route_rows(self.rows, [ROW_REFUSED])
        transcript = trg.write_transcript([trg.human("open a PR"), trg.assistant_text(reply)], self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": transcript, "stop_hook_active": False,
                "cwd": self.run_dir, "session_id": "cannot-sid-1"}
        env = hook_base.surface_env(dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home), "local")
        env[hook_base.ROUTE_ROWS_ENV] = self.rows
        run = subprocess.run([sys.executable, "-c", OPENS_CODE, trg.REPORT_GUARD], input=json.dumps(hook),
                             capture_output=True, text=True, timeout=15, env=env)
        self.assertEqual(run.returncode, 0, "the Stop hook exited non-zero: " + run.stderr[-300:])
        self.assertNotIn("Traceback", run.stderr, "the Stop hook crashed: " + run.stderr[-300:])
        _, mark, tail = run.stderr.rpartition("OPENED ")
        self.assertTrue(mark, "the probe did not finish: " + run.stderr[-300:])
        return run.stdout.strip(), json.loads(tail), refusals, transcript

    def test_cc_cost_a_claim_free_reply_adds_no_read_of_the_refusals_or_route_file(self):
        # Catches: the check reading the refusals file or the route rows on a reply that claims nothing. Two readers that
        # predate the check open the refusals file on every Stop (the route flags, and the settling of the file). So the
        # proof is a difference: the same reply with one claim line adds exactly one read of the refusals file, and the
        # claim-free reply reads the route rows not at all.
        refuse = "`%s` refusal was right." % OPEN_PR
        free_out, free_opened, refusals, transcript = self.opened_by_stop(refuse + " Opening the PR next.")
        self.assertEqual(free_out, "", "a claim-free reply was judged: %s" % free_out)
        self.assertNotIn(self.rows, free_opened, "the route rows were read on a claim-free reply")
        self.assertIn(transcript, free_opened)
        _, claimed_opened, _, _ = self.opened_by_stop(refuse + " I can't open the PR.")
        extra = claimed_opened.count(refusals) - free_opened.count(refusals)
        self.assertEqual(extra, 1, "the refusals file read %d more times on a claim line, expected one" % extra)

    # ---- the claim cases: the blocker clause, the script try, the check words, the api.github.com dot, the act words a
    # window may not cross, and the semicolon scan. A red line is a claim the check must read. A control is a line the
    # check must leave as it is, and each control says what it passes or blocks.

    def test_cc_red_blocker_because_ci_is_no_claim(self):
        # Catches: a claim whose clause carries a blocker (because CI) read as a claim with no try. A blocker is a true reason,
        # so the line is no hand-off. The turn holds no try, so only the blocker skip can clear it.
        line = "I can't merge the PR because CI is red."
        out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
        self.assert_passes(out, "a claim whose clause carries a blocker (because CI)")

    def test_cc_red_blocker_while_the_batch_run_is_no_claim(self):
        # Catches: a claim whose clause carries a blocker (while the batch run) read as a claim with no try.
        line = "I cannot merge it while the batch run is in progress."
        out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
        self.assert_passes(out, "a claim whose clause carries a blocker (while the batch run)")

    def test_cc_red_blocker_rule_id_after_the_act_is_no_claim(self):
        # Catches: a claim that names its hyphenated rule id in parentheses after the act, read as a claim with no try.
        line = "I can't push to main (git-main-only-by-pr)."
        out = self.stop([trg.human("push to main"), trg.assistant_text(line)])
        self.assert_passes(out, "a claim that names its rule id after the act")

    def test_cc_green_connect_failure_because_clause_still_blocks(self):
        # Control: a connect failure is no blocker, so the because clause does not skip the claim. The
        # notice is no try, so the line blocks as no try.
        line = "I can't open the PR because the MCP server failed to connect."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_could_not_open_with_only_a_notice_still_blocks(self):
        # Control: a bare claim whose only evidence is a notice. The notice is no try, so it blocks.
        line = "I could not open the PR."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_plain_cannot_merge_with_no_try_or_cite_still_blocks(self):
        # Control: with no blocker, no try and no cite, the claim blocks.
        line = "I cannot merge the PR."
        out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_failed_merge_tool_call_is_a_try_of_pr_merge(self):
        # Catches: a failed call to the repo's merge tool read as no try of pr-merge, so a claim it backs blocks. The bare
        # name and the installed path both name the merge tool.
        for command, line in (("merge 12", "I couldn't merge PR 12: `merge 12` exited 1."),
                              ("~/.claude/bin/merge 12", "I couldn't merge PR 12: `~/.claude/bin/merge 12` exited 1.")):
            with self.subTest(command=command):
                out = self.stop([trg.human("merge PR 12"), *failed_bash(command, "tu_m"), landed_reply(line)])
                self.assert_passes(out, "a failed `%s` backs a pr-merge claim" % command)

    def test_cc_red_failed_open_pr_script_is_a_try_of_pr_open(self):
        # Catches: a failed repo script whose name holds the act word (open-pr) read as no try of pr-open.
        line = "I could not open the PR: `open-pr.sh` exited 1."
        out = self.stop([trg.human("open a PR"), *failed_bash("./open-pr.sh", "tu_o"), landed_reply(line)])
        self.assert_passes(out, "a failed open-pr.sh backs a pr-open claim")

    def test_cc_green_failed_unrelated_script_does_not_back_pr_open(self):
        # Control: a failed script whose name holds no act word backs no act, so the claim blocks.
        line = "I could not open the PR; `lint.sh` exited 1."
        out = self.stop([trg.human("open a PR"), *failed_bash("./lint.sh", "tu_l"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_present_tense_check_word_names_the_check(self):
        # Catches: check words in the past tense only (tried, failed), so a line that names its failed try in the present
        # tense (fails, returns) reads as naming no check. Only the check word differs from the named-check case.
        clauses = ("the create tool refuses it.", "the create tool denies it.", "the create tool rejects it.",
                   "the create tool fails.", "the create tool returns an error.", "the create tool errors.")
        for clause in clauses:
            line = "I can't open the PR: " + clause
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), *failed_pr_create(), landed_reply(line)])
                self.assert_passes(out, "a present-tense check word names the failed try: %r" % line)

    def test_cc_red_api_github_dot_does_not_end_the_clause(self):
        # Catches: the dot in api.github.com read as the end of the clause, so the github-reach phrase never reaches its
        # route and the claim reads as no act.
        line = "I can't reach api.github.com from here."
        out = self.stop([trg.human("reach GitHub"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_github_dot_com_still_reads_as_github_reach(self):
        # Control: a dot inside github.com is also no clause end, and the claim still blocks as no try.
        line = "I can't reach github.com from here."
        out = self.stop([trg.human("reach GitHub"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_git_push_with_a_command_word_before_the_verb_is_a_claim(self):
        # Catches: "git" between the phrase and the verb, so "I can't git push" reads as no push claim.
        line = "I can't git push the branch."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_git_push_claim_with_its_failed_try_and_check_passes(self):
        # Control: the same claim backed by a failed git push, named. The fix must keep the try and check.
        line = "I can't git push the branch: `git push` failed."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         landed_reply(line)])
        self.assert_passes(out, "a git push claim backed by its failed try, named")

    def test_cc_red_draft_github_pull_request_is_a_pr_open_claim(self):
        # Catches: the object window of pr-open too short for "a draft GitHub pull request", so the claim reads as no act.
        line = "I cannot open a draft GitHub pull request."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_call_count_of_a_long_semicolon_sentence_grows_linearly(self):
        # Catches: the semicolon list that _claim builds for each phrase, so a long semicolon sentence costs a quadratic
        # number of calls. The builtin calls of the Stop run grow by 2 from 500 to 1,000 phrases for a linear check and by
        # 4 for a quadratic one, once the count for no phrases is taken off. A count reads no clock (test-practices P5).
        def calls(phrases):
            run = self.reply_run(" ".join(["I can't open the PR;"] * phrases) + ".", CALLS_CODE, timeout=120)
            self.assertIn("CALLS ", run.stderr, "the call count did not print: " + run.stderr[-300:])
            return int(run.stderr.rpartition("CALLS ")[2])

        base, small, large = calls(0), calls(500), calls(1000)
        growth = (large - base) / float(small - base)
        self.assertLess(growth, 3, "the calls grow %.2fx from 500 to 1,000 phrases; a linear check grows 2x" % growth)

    def test_cc_green_full_size_semicolon_sentence_keeps_its_block(self):
        # Control at full size: a 160 KB sentence of 7,800 phrases, each a claim with no try. The block stays, and it is
        # the no-try variant. It reads no clock, so a fix must keep it green.
        run = self.reply_run(" ".join(["I can't open the PR;"] * 7800) + ".", timeout=120)
        out = json.loads(run.stdout) if run.stdout.strip() else None
        self.assertIsNotNone(out, "no block came for the 160 KB sentence")
        self.assertEqual(out.get("decision"), "block", "the 160 KB sentence was not blocked")
        self.assertIn(HEAD, out.get("reason", ""), "the block for the 160 KB sentence is not the cannot-claim guard")
        self.assertIn(NO_TRY, out.get("reason", ""), "the 160 KB sentence has the wrong variant")

    # ---- a blocker word followed by a tool or connector noun is an outage, not a blocker. A lock in index.lock is a file,
    # not the lock blocker. A blocker in the same sentence skips the claim, before or after it. Up to four words may sit
    # between the verb and PR, none of them a preposition word (in, on, per); a hyphenated word such as in-progress is no
    # preposition. A make target or an npm run script whose name holds push is a try of push; a bare npm push is not,
    # since npm has no push. A red line is a claim the check must read.

    def test_cc_red_f1_outage_checks_tool_failed_to_connect_blocks(self):
        # Catches: the blocker word "checks" followed by a tool noun read as a blocker, so an outage reason passes as no claim.
        line = "I can't open the PR because the checks tool failed to connect."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_f1_outage_review_tool_timed_out_blocks(self):
        # Catches: the blocker word "review" followed by a tool noun read as a blocker, so a timed-out tool passes as no claim.
        line = "I can't open the PR because the review tool timed out."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_f1_outage_batch_tool_timed_out_blocks(self):
        # Catches: the blocker words "the batch" followed by a tool noun read as a blocker, so a timed-out tool passes as no claim.
        line = "I can't open the PR because the batch tool timed out."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_f1_outage_connector_on_hold_blocks(self):
        # Catches: the blocker word "hold" in "is on hold" read as a blocker after a connector noun, so the outage passes.
        line = "I can't open the PR because the connector is on hold."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_f1_outage_connector_lock_expired_blocks(self):
        # Catches: the blocker word "lock" after a connector noun read as a blocker, so an expired connector lock passes.
        line = "I can't open the PR because the connector lock expired."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_read_only_parenthesis_is_a_claim_and_blocks(self):
        # Control: "(read-only)" has one hyphen, so it is no rule id. The claim it follows stays a claim and blocks.
        line = "I can't push to the remote (read-only)."
        out = self.stop([trg.human("push to the remote"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_f2_noun_between_the_verb_and_pr_is_no_claim(self):
        # Catches: the pr-open window reading any noun between the verb and PR, so "open the logs for PR 12" claims pr-open.
        for line in ("I can't open the logs for PR 12.", "I can't open the diff for PR 12.",
                     "I can't create the tag for PR 12."):
            with self.subTest(line=line):
                out = self.stop([trg.human("show the logs"), trg.assistant_text(line)])
                self.assert_passes(out, "a noun other than a, an, the, new, draft or GitHub sits before PR: %r" % line)

    def test_cc_green_f2_allowed_words_before_pr_still_block(self):
        # Control: a, an, the, new, draft and GitHub may sit between the verb and PR, so these claims still block.
        for line in ("I can't open the new PR.", "I can't open a draft GitHub pull request."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_f3_index_lock_is_no_blocker(self):
        # Catches: "lock" inside the path index.lock read as the lock blocker, so a push that git's index lock stops passes.
        line = "I can't push because index.lock is in the way."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_f4_blocker_before_or_after_the_clause_is_no_claim(self):
        # Catches: a blocker read only in the clause the phrase starts, so a blocker before it or after a semicolon in the
        # same sentence does not skip the claim. Both lines are claims with a blocker in the sentence, so both pass.
        for line in ("Because CI is red, I can't merge the PR.", "I can't merge the PR; CI is red."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a blocker in the same sentence: %r" % line)

    def test_cc_red_f5_failed_make_push_is_a_try_of_push(self):
        # Catches: a make target that pushes read as no try of push. The first plain argument, push, names the act.
        line = "I could not push: `make push` exited 2."
        out = self.stop([trg.human("push the branch"), *exit_bash("make push", 2, "tu_mk"), landed_reply(line)])
        self.assert_passes(out, "a failed make push backs a push claim")

    def test_cc_red_f5_failed_npm_run_push_docs_is_a_try_of_push(self):
        # Catches: an npm run script whose name holds the act word read as no try of push. The first plain argument after
        # run names the script.
        line = "I could not push: `npm run push-docs` exited 1."
        out = self.stop([trg.human("push the docs"), *exit_bash("npm run push-docs", 1, "tu_np"), landed_reply(line)])
        self.assert_passes(out, "a failed npm run push-docs backs a push claim")

    def test_cc_green_f5_failed_make_test_is_no_try_of_push(self):
        # Control: a failed make target that names no act word backs no push, so the claim blocks.
        line = "I could not push: `make test` exited 2."
        out = self.stop([trg.human("push the branch"), *exit_bash("make test", 2, "tu_mt"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    # ---- the pr-open object window, the slugs in parentheses that skip a claim, the scripts named for a test, and the
    # blocker states and joined blockers. Each case asserts behaviour only, so no identifier is named here.

    def test_cc_red_pr_with_another_object_noun_still_claims(self):
        # Catches: the pr-open object window that admits only a, an, the, new, draft and GitHub, so "the integration PR"
        # and "two PRs" read as no act. Each line is a claim, and a notice is no try, so each blocks as no try.
        lines = ("I can't open the integration PR.", "I can't open a follow-up PR.", "I can't open another PR.",
                 "I can't open this PR.", "I can't open my PR.", "I can't create the batch PR.",
                 "I can't create the follow-up pull request.", "I can't create two PRs.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), notice("github: failed to connect"),
                                 trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_pr_for_another_number_is_no_claim(self):
        # Control: a preposition (for, of, to) after the object ends the window, so these are no claim.
        lines = ("I can't open the logs for PR 12.", "I can't open the diff for PR 12.",
                 "I can't create the tag for PR 12.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("show the logs"), notice("github: failed to connect"),
                                 trg.assistant_text(line)])
                self.assert_passes(out, "a noun phrase for another PR number: %r" % line)

    def test_cc_red_slug_in_parens_skips_only_a_real_rule_id(self):
        # Catches: any slug of two or more hyphens in parentheses read as a rule id, so a slug that names no rule or
        # decision skips the claim. The first three lines are claims with no try; the last names a real rule, so it passes.
        for human, line in (("push the branch", "I can't push the branch (cannot-claim-follow-up)."),
                            ("open a PR", "I could not open the PR (connect-failure-notice)."),
                            ("push", "I can't push (pre-push-hook).")):
            with self.subTest(line=line):
                out = self.stop([trg.human(human), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)
        with self.subTest(line="I can't push to main (git-main-only-by-pr)."):
            out = self.stop([trg.human("push to main"), trg.assistant_text("I can't push to main (git-main-only-by-pr).")])
            self.assert_passes(out, "a slug that names a real rule id")

    def test_cc_red_failed_test_script_is_no_try(self):
        # Catches: a script whose name holds an act word and also a test name (test_merge.py, test-push.sh) read as a try
        # of that act. A failed test run backs no claim of the act it tests.
        for human, command, line in (
                ("merge PR 12", "python3 merge/test_merge.py",
                 "I could not merge PR 12: `python3 merge/test_merge.py` exited 1."),
                ("push the branch", "./test-push.sh", "I could not push: `./test-push.sh` exited 1.")):
            with self.subTest(command=command):
                out = self.stop([trg.human(human), *failed_bash(command, "tu_t"), landed_reply(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_failed_push_script_still_backs_push(self):
        # Control: a failed script named for the act, with no test name, is still a try of that act.
        line = "I could not push: `./push.sh` exited 1."
        out = self.stop([trg.human("push the branch"), *failed_bash("./push.sh", "tu_p"), landed_reply(line)])
        self.assert_passes(out, "a failed push script, named, backs a push claim")

    def test_cc_red_blocker_states_and_joined_blockers_pass(self):
        # Catches: a blocker that holds only in a list of states (still running, haven't passed, is red), or only with a
        # because or while clause, so a true blocker joined to the claim by a comma, a semicolon, a colon or parens blocks.
        lines = ("CI is still running, so I can't merge.", "I can't merge PR 12: CI is red.",
                 "I can't merge PR 12 (CI is red).", "CI is red; I can't merge the PR.",
                 "checks haven't passed, so I can't merge.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a blocker that holds the claim: %r" % line)

    def test_cc_green_connect_failure_after_a_colon_still_blocks(self):
        # Control: a connect failure after a colon is no blocker, so the claim blocks as no try.
        line = "I can't open the PR: the MCP server failed to connect."
        out = self.stop([trg.human("open a PR"), notice("github: failed to connect"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    # ---- an installed copy: the hook's lint and hooks folders under a config dir that holds only a pointer line to the
    # checkout. The copy has no decisions of its own, so a rule id is real only when the pointer checkout names it.

    def installed_guard(self):
        """Install the hook into this case's config dir, as the installer does: the folders landed-dirs.txt names that the
        hook reads (lint, hooks and output-styles, the file the rule anchors come from), and a CLAUDE.md that holds only
        the pointer line. Returns the copy of report_guard.py the Stop hook runs."""
        tracked_tree.copy_tracked(self.cfg, "lint", "hooks", "output-styles")
        with open(os.path.join(self.cfg, "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@%s/CLAUDE.md\n" % os.path.dirname(HERE))
        return os.path.join(self.cfg, "lint", "report_guard.py")

    def test_cc_red_installed_copy_reads_a_rule_id_from_the_pointer_checkout(self):
        # Catches: the rule-id check reading the pointer checkout only once the guard has loaded. An installed hook judges
        # the claim before that load, so the pointer is never read, the real id is no id, and the claim blocks.
        line = "I can't push to main (git-main-only-by-pr)."
        out = self.stop([trg.human("push to main"), trg.assistant_text(line)], guard=self.installed_guard())
        self.assert_passes(out, "a real rule id, read from the pointer checkout of an installed copy")

    def test_cc_green_installed_copy_still_blocks_a_slug_that_names_no_rule(self):
        # Control: a slug that no rule or decision holds is still no rule id in an installed copy.
        line = "I could not open the PR (connect-failure-notice)."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)], guard=self.installed_guard())
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_recovered_merge_of_another_pr_does_not_cancel_a_failed_merge(self):
        # Catches: a later merge that recovered on PR 12 read as cancelling the failure of PR 13, so the claim about PR 13
        # passed. A later success cancels a failure only for the same target.
        line = "I could not merge PR 13."
        out = self.stop([trg.human("merge PR 13"), *failed_bash("merge 12", "tu_1"), *ok_bash("merge 12", "tu_2"),
                         *failed_bash("merge 13", "tu_3"), landed_reply(line)])
        self.assert_blocks(out, line)

    def test_cc_green_a_recovered_make_push_still_blocks_a_push_claim(self):
        # Control: a make push that recovered is another call from ./push.sh, so the claim that names no check still blocks.
        line = "I could not push the branch."
        out = self.stop([trg.human("push the branch"), *failed_bash("./push.sh", "tu_1"), *ok_bash("make push", "tu_2"),
                         landed_reply(line)])
        self.assert_blocks(out, line)

    def test_cc_green_a_recovered_open_pr_script_for_another_branch_still_blocks(self):
        # Control: a recovered open-pr.sh for feature is another target from other, so the claim about other still blocks.
        line = "I could not open the PR for other."
        out = self.stop([trg.human("open the PR for other"), *failed_bash("./open-pr.sh other", "tu_1"),
                         *ok_bash("./open-pr.sh feature", "tu_2"), landed_reply(line)])
        self.assert_blocks(out, line)

    def test_cc_red_a_status_after_a_colon_or_after_got_names_the_check(self):
        # Catches: a bare status after a colon, or a number after got, read as naming no check, so a refused merge whose
        # status was named blocked. A diff size is no status (the case above).
        for line in ("I cannot merge PR 12: 403 Forbidden.", "I cannot merge PR 12, got a 403."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
                self.assert_passes(out, "a refused merge whose status is named")

    def test_cc_red_a_peer_ack_after_a_send_does_not_end_the_turn(self):
        # Catches: a peer ack after a send read as the start of a new turn, so the failed push before it stopped counting and
        # the push claim blocked with no try. An ack starts no turn.
        line = "I cannot push; `git push` exited 1."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         use("mcp__claude-code-remote__send_message", {"session_id": "session_peer", "message": "status?"},
                             "tu_s"),
                         done("tu_s", "sent"), trg.peer_msg("got it", from_session="session_peer"), landed_reply(line)])
        self.assert_passes(out, "a push claim whose failed try sits before a peer ack in the same turn")

    def test_cc_red_emphasis_around_the_phrase_or_the_subject_still_claims(self):
        # Catches: emphasis marks around the phrase or the subject read past the subject test, so the claim passed as no claim.
        for line in ("I **cannot** merge PR 12.", "I *cannot* merge PR 12.", "**I cannot** merge PR 12.",
                     "I *can't* merge PR 12."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_currently_unable_past_push_recovered_by_a_later_push_is_no_claim(self):
        # Catches: an adverb between was and unable read as a present claim, so a past failure of a push that a later push
        # recovered blocked. An adverb after was keeps the phrase past.
        line = "I was currently unable to push at first; I rebased and pushed."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p1"),
                         *ok_bash("git push origin HEAD", "tu_p2"), landed_reply(line)])
        self.assert_passes(out, "a past failure of a push that a later push recovered, with an adverb after was")

    def test_cc_red_a_permission_or_allowed_claim_has_no_try(self):
        # Catches: "not allowed", "do not have permission" and "not going to be able" read as no act claim, so a claim that a
        # merge or a push cannot be done passed with no try.
        for prompt, line in (("merge PR 12", "I am not allowed to merge PR 12."),
                             ("merge PR 12", "I do not have permission to merge PR 12."),
                             ("push the branch", "I'm not going to be able to push.")):
            with self.subTest(line=line):
                out = self.stop([trg.human(prompt), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_bare_cannot_merge_the_branch_still_blocks(self):
        # Control: "I cannot merge the branch." is a bare claim with no try, so it blocks.
        line = "I cannot merge the branch."
        out = self.stop([trg.human("merge the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_reason_adjective_after_a_refused_merge_names_no_check(self):
        # Catches: "protected" read as a reason verb, so the adjective after the claim named a check and the refused merge
        # passed as named.
        line = "I cannot merge PR 12, a protected branch."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_check_of_another_act_in_an_earlier_sentence_names_no_check(self):
        # Catches: a check named for another act, a create that returned 403, read as naming the check of this merge claim.
        line = "I cannot merge PR 12, a protected branch."
        reply = "`gh pr create` returned 403. " + line
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(reply)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_create_cancelled_by_another_head_does_not_cancel_the_first(self):
        # Catches: two creates with empty targets cancelling each other, so the failed create of b1 backed no claim. A create is
        # cancelled only by a success for its own --head; a create with no --head has no target, so no success cancels it
        # (the flagless case is the next test).
        line = "I could not open the PR for b1 at first."
        out = self.stop([trg.human("open the PR for b1"), *failed_bash("gh pr create --draft --head b1", "tu_1"),
                         *ok_bash("gh pr create --head b2", "tu_2"), landed_reply(line)])
        self.assert_blocks(out, line)

    def test_cc_red_a_flagless_create_is_cancelled_by_no_success(self):
        # Catches: two creates with no --head, each with an empty target, cancelling each other, so the failed create backed
        # no claim and its failure passed. A create with no --head names no target, so no success cancels it.
        line = "I could not open the PR for b1 at first, so please open it yourself."
        out = self.stop([trg.human("open the PR for b1"), *failed_bash("gh pr create --draft", "tu_1"),
                         *ok_bash("gh pr create --base main", "tu_2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_merge_on_another_repo_does_not_cancel_a_flagless_merge(self):
        # Catches: a merge with --repo read as the same PR as a merge with no repo, so its success cancelled the failed merge.
        line = "I could not merge PR 12 at first."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_1"),
                         *ok_bash("gh pr merge --repo other/x 12", "tu_2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_prose_check_word_about_another_act_names_no_check(self):
        # Catches: "failed" in a sentence about a push read as naming the check of a merge claim, so a refused merge passed.
        line = "I could not merge PR 12."
        reply = "The push failed. " + line
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(reply)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_status_sent_or_came_back_names_the_check(self):
        # Catches: "sent back" and "came back" before a status count read as a reason verb or a check word, so a refused
        # merge whose status was named blocked.
        for line in ("I could not merge PR 12: the server sent back 403.", "I could not merge PR 12: it came back 403."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
                self.assert_passes(out, "a refused merge whose status is named after sent back or came back")

    def test_cc_red_network_checks_failing_is_an_outage_for_a_merge_claim(self):
        # Catches: "the network checks are failing" read as a CI check blocker, so the merge claim beside it passed. A network
        # check is an outage, so the claim has no try and blocks.
        line = "I cannot merge PR 12; the network checks are failing."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_failing_to_pass_go_green_or_complete_names_the_blocker(self):
        # Catches: "failing to" read as an outage for any verb, so a CI state that failed to pass, go green or complete blocked
        # as having no try. Only failing to start, connect, run, load or reach is an outage.
        for line in ("I can't merge PR 12 because the checks are failing to pass.",
                     "I can't merge PR 12 because CI is failing to go green.",
                     "I can't merge PR 12 because CI is still failing to complete."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_passes(out, "a merge claim whose blocker is CI failing to pass, go green or complete")

    def test_cc_green_a_failing_to_run_load_or_reach_is_an_outage(self):
        # Control: failing to run, load or reach is an outage, so the merge claim beside it has no try and blocks.
        for line in ("I can't merge PR 12 because CI is failing to run.",
                     "I can't merge PR 12 because CI is failing to load.",
                     "I can't merge PR 12 because CI is failing to reach the server."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_ci_failing_with_lint_errors_or_a_colon_names_the_blocker(self):
        # Catches: "CI is failing" followed by lint errors, a lint job or a colon read as an outage, so a merge claim that CI
        # blocks blocked with no try. A CI state names the blocker of a merge.
        for line in ("I can't merge PR 12 because CI is failing with lint errors.",
                     "I can't merge PR 12 because CI is failing: lint job.",
                     "CI is failing: I can't merge PR 12."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_passes(out, "a merge claim whose blocker is CI failing")

    def test_cc_red_a_lead_in_word_or_clause_before_the_phrase_is_no_reason(self):
        # Catches: a lead-in word before the phrase read as a reason, so a line with no check named after a failed try passed.
        # Each line here has no clause with a verb before the phrase, so none of them names a check.
        for prompt, act, line in (
                ("push the branch", "git push origin HEAD", "Unfortunately, I cannot push."),
                ("merge PR 12", "gh pr merge 12", "Sorry, I could not merge PR 12."),
                ("push the branch", "git push origin HEAD", "However, I could not push."),
                ("push the branch", "git push origin HEAD", "I tried; I cannot push."),
                ("push the branch", "git push origin HEAD", "I cannot push, but I can open a PR.")):
            with self.subTest(line=line):
                out = self.stop([trg.human(prompt), *failed_bash(act, "tu_f"), landed_reply(line)])
                self.assert_blocks(out, line)

    def test_cc_red_emphasis_marks_around_the_phrase_still_claim(self):
        # Catches: bold, italic and underscore marks inside the phrase read past the phrase search, so the claim passed as no
        # claim. Each line has no try and must block.
        for prompt, line in (("merge PR 12", "I am **unable** to merge PR 12."),
                             ("push the branch", "I could **not** push."),
                             ("push the branch", "I am **not** able to push."),
                             ("push the branch", "I was **unable** to push."),
                             ("push the branch", "I am not **allowed** to push."),
                             ("push the branch", "I _cannot_ push."),
                             ("push the branch", "I __cannot__ push.")):
            with self.subTest(line=line):
                out = self.stop([trg.human(prompt), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_status_after_a_comma_semicolon_or_dash_names_the_check(self):
        # Catches: a status set off by a comma, a semicolon or a dash, or after answered, read as naming no check, so a refused
        # merge whose status was named blocked.
        for line in ("I cannot merge PR 12, 403 Forbidden.", "I cannot merge PR 12; 403 Forbidden.",
                     "I cannot merge PR 12 — 403 Forbidden.", "I cannot merge PR 12 - 403.",
                     "I cannot merge PR 12; the server answered 403 Forbidden."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
                self.assert_passes(out, "a refused merge whose status is named after a comma, semicolon, dash or answered")

    def test_cc_red_a_prior_code_span_of_another_route_names_no_check(self):
        # Catches: a code span that names a command of another route read as naming the check of this merge claim, so a
        # refused merge passed as named. A prior span names a check only when it names a route of this act.
        line = "I cannot merge PR 12."
        reply = "`ls` printed a list. " + line
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(reply)])
        self.assert_blocked_for(out, NO_CHECK, line)

    # ---- a later success cancels a failed try of the same call. A flagless gh pr call names no PR, so its own arguments
    # are its identity: an identical call cancels its failure, and a differing one cancels nothing.

    def test_cc_red_a_flagless_read_success_cancels_its_failure(self):
        # Catches: a later success of a flagless gh pr read (view, status, checks, list) skipped as an unknown target, so the
        # failure of the same read stood and the past claim named no check.
        line = "I could not reach GitHub at first."
        for verb in ("view", "status", "checks", "list"):
            with self.subTest(verb=verb):
                out = self.stop([trg.human("check the PR"), *failed_bash("gh pr " + verb, "tu_f"),
                                 *ok_bash("gh pr " + verb, "tu_o"), landed_reply(line)])
                self.assert_passes(out, "a failed, then ok, flagless gh pr %s" % verb)

    def test_cc_green_a_flagless_read_failure_with_no_success_still_blocks(self):
        # Control: the same failed flagless read with no later success. The past claim names no check, so it blocks.
        line = "I could not reach GitHub at first."
        out = self.stop([trg.human("check the PR"), *failed_bash("gh pr view", "tu_f"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_green_a_numbered_read_success_cancels_its_failure(self):
        # Control: a numbered read has a known target, so its later success already cancels its failure. The line passes.
        line = "I could not reach GitHub at first."
        out = self.stop([trg.human("check the PR"), *failed_bash("gh pr view 12", "tu_f"),
                         *ok_bash("gh pr view 12", "tu_o"), landed_reply(line)])
        self.assert_passes(out, "a failed, then ok, numbered gh pr view")

    def test_cc_red_an_identical_retry_of_a_flagless_create_cancels_its_failure(self):
        # Catches: a flagless create keyed as an unknown target, so its identical retry, which succeeded, did not cancel the
        # failed create. The retry names the same arguments, so it is the same call.
        call = "gh pr create --draft --title T --body B"
        for line in ("I could not open the PR on the first try, so I retried.",
                     "I was unable to open the PR at first, then it worked."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), *failed_bash(call, "tu_1"), *ok_bash(call, "tu_2"),
                                 landed_reply(line)])
                self.assert_passes(out, "an identical retry of a failed flagless create: %r" % line)

    def test_cc_red_an_identical_retry_of_a_flagless_merge_cancels_its_failure(self):
        # Catches: a flagless merge keyed as an unknown target, so its identical retry, which succeeded, did not cancel the
        # failed merge and the past claim named no check.
        call = "gh pr merge --squash"
        line = "I could not merge the PR at first, then it worked."
        out = self.stop([trg.human("merge the PR"), *failed_bash(call, "tu_1"), *ok_bash(call, "tu_2"),
                         landed_reply(line)])
        self.assert_passes(out, "an identical retry of a failed flagless merge")

    def test_cc_green_a_differing_flagless_create_still_blocks(self):
        # Control: a create with --draft failed, then a create with --base main succeeded. The calls differ, so the success
        # cancels nothing and the past claim names no check.
        line = "I could not open the PR on the first try, so I retried."
        out = self.stop([trg.human("open a PR"), *failed_bash("gh pr create --draft", "tu_1"),
                         *ok_bash("gh pr create --base main", "tu_2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_green_a_differing_merge_of_another_repo_still_blocks(self):
        # Control: a merge of PR 12 failed, then a merge of PR 12 in another repo succeeded. The two targets differ.
        line = "I could not merge the PR at first, then it worked."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_1"),
                         *ok_bash("gh pr merge --repo other/x 12", "tu_2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_green_a_differing_flagless_merge_still_blocks(self):
        # Control: a flagless merge with --squash failed, then one with --rebase succeeded. The calls differ, so no cancel.
        line = "I could not merge the PR at first, then it worked."
        out = self.stop([trg.human("merge the PR"), *failed_bash("gh pr merge --squash", "tu_1"),
                         *ok_bash("gh pr merge --rebase", "tu_2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_red_a_count_after_sent_back_names_no_check(self):
        # Catches: "sent back" read as a status before any number, so "450 files" named the check of a refused merge. A count
        # of units is no HTTP status, the same unit exclusion as CANNOT_CHECK_RE.
        line = "I could not merge PR 12: it sent back 450 files."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_green_a_status_after_sent_back_still_names_the_check(self):
        # Control: a real status after "sent back" still names the check of the refused merge.
        line = "I could not merge PR 12: it sent back 403."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_passes(out, "a refused merge whose status 403 is sent back")

    # ---- a local merge is no pr-merge try, and a status in an ok result is no failure

    def test_cc_red_a_failed_local_merge_is_no_try_of_a_pr_merge(self):
        # Catches: a failed `git merge origin/main` read as a try of merging the PR, so the line that says the PR cannot be
        # merged passed. A local merge is no pr-merge route, so the turn holds no try of that act: the no-try variant fires.
        line = "I cannot merge PR 12: `git merge origin/main` conflicted."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("git merge origin/main", "tu_g"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_an_ok_result_quoting_http_500_is_no_failed_try(self):
        # Catches: an HTTP 500 quoted in the output of an ok `gh pr list` read as a failure, so the line that says GitHub
        # cannot be reached passed. A status counts as a failure only in an error result: the error flag or a non-zero exit.
        line = "I cannot reach GitHub: `gh pr list` returned nothing."
        out = self.stop([trg.human("reach GitHub"), use("Bash", {"command": "gh pr list"}, "tu_l"),
                         done("tu_l", "HTTP 500 quoted in the log; no PRs listed."), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_failed_gh_pr_merge_still_backs_the_merge_claim(self):
        # Control: a failed `gh pr merge 12` is a pr-merge try, so the merge claim that names it passes.
        line = "I cannot merge PR 12: `gh pr merge 12` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_passes(out, "a failed gh pr merge 12 backs the merge claim")

    def test_cc_green_an_error_result_with_http_500_still_backs_the_reach_claim(self):
        # Control: an error result that carries HTTP 500 is a failed try of GitHub reach, so the reach claim passes.
        line = "I cannot reach GitHub: `gh pr list` returned nothing."
        out = self.stop([trg.human("reach GitHub"), use("Bash", {"command": "gh pr list"}, "tu_l"),
                         done("tu_l", "HTTP 500 Internal Server Error", error=True), landed_reply(line)])
        self.assert_passes(out, "an error result with HTTP 500 backs the reach claim")


    def test_cc_red_a_claim_on_a_non_pr_or_docs_object_is_no_claim(self):
        # Catches: a merge, an open or an update whose object is not a PR, read as a PR claim with no try, so a claim about
        # config files, CI logs or docs blocked.
        for prompt, line in (("merge the config files", "I can't merge these two config files."),
                             ("open the CI logs", "I can't open the PR's CI logs."),
                             ("update the docs", "I can't update the docs for PR 12.")):
            with self.subTest(line=line):
                out = self.stop([trg.human(prompt), trg.assistant_text(line)])
                self.assert_passes(out, "a claim whose object is not a PR")

    def test_cc_red_a_run_of_gh_pr_create_is_a_claim(self):
        # Catches: a run of gh pr create read as no PR claim, so the claim that it cannot run passed with no try.
        line = "I can't run gh pr create."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)


    # ---- notes with `Fix: step:clause-parser-claims`: the forms, outage nouns and merge-tool targets the clause parser reads

    def test_cc_red_an_adverb_before_unable_to_is_a_claim(self):
        # Catches: an -ly adverb that ADVERBS does not list ("temporarily", "presently") between the verb and "unable to", so
        # the claim that the act cannot be done read as no claim and passed with no try.
        for prompt, line in (("push the branch", "I am temporarily unable to push."),
                             ("merge PR 12", "I am presently unable to merge PR 12.")):
            with self.subTest(line=line):
                out = self.stop([trg.human(prompt), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_not_authorized_no_access_lack_permission_or_blocked_from_is_a_claim(self):
        # Catches: "not authorized to", "do not have access to", "lack permission to" and "blocked from" missing from
        # CANNOT_FORMS, so a claim that an act cannot be done read as no claim and passed with no try.
        for prompt, line in (("push the branch", "I am not authorized to push."),
                             ("merge PR 12", "I do not have access to merge PR 12."),
                             ("push the branch", "I lack permission to push."),
                             ("push the branch", "I am blocked from pushing.")):
            with self.subTest(line=line):
                out = self.stop([trg.human(prompt), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_merge_blamed_on_an_auth_proxy_or_clone_failure_has_no_try(self):
        # Catches: "auth checks", "proxy checks", "failing to authenticate" and "failing to clone" read as a blocker of the
        # merge, so the merge claim beside them passed as backed. None of them names a blocker, so the claim has no try.
        for line in ("I can't merge PR 12 because the auth checks are failing.",
                     "I can't merge PR 12 because the proxy checks are failing.",
                     "I can't merge PR 12 because CI is failing to authenticate.",
                     "I can't merge PR 12 because CI is failing to clone."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_url_merge_success_cancels_a_failed_merge_by_number_of_its_repo(self):
        # Catches: a merge success whose target is the PR's URL keyed by its number alone, so the failed `gh pr merge 12
        # --repo o/r` was not cancelled by a later success of that PR by URL, and the past-tense line about it blocked. A
        # URL keys by its repo and number, so it cancels a failure whose --repo is the URL's repo.
        line = "I could not merge PR 12 at first."
        by_number = [trg.human("merge PR 12"), *failed_bash("gh pr merge 12 --repo o/r", "tu_m1"),
                     *ok_bash("gh pr merge 12 --repo o/r", "tu_m2"), landed_reply(line)]
        by_url = [trg.human("merge PR 12"), *failed_bash("gh pr merge 12 --repo o/r", "tu_m1"),
                  *ok_bash("gh pr merge https://github.com/o/r/pull/12", "tu_m2"), landed_reply(line)]
        # Scope first (P7): the number form is the control, so the URL form is the only change between the two runs.
        self.assert_passes(self.stop(by_number), "the control: a later success of PR 12 by number and --repo o/r cancels it")
        self.assert_passes(self.stop(by_url), "a later success of PR 12 by its URL cancels a failure whose --repo is o/r")

    def test_cc_red_a_masked_status_span_does_not_hide_a_claim(self):
        # Catches: the code span `not connected` between a colon and a semicolon. The later separator is dropped, so the
        # claim's clause starts at the colon and its negation is read from the masked span. The turn has no try.
        line = "MCP status: `not connected`; I cannot open a PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_masked_quoted_negation_does_not_hide_a_claim(self):
        # Catches: the quote "not connected" between a colon and a semicolon, read as a negation of the claim after it.
        # The turn has no try.
        line = 'GitHub MCP said: "not connected"; I can\'t open a PR.'
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_masked_no_tools_before_a_comma_does_not_hide_a_claim(self):
        # Catches: the code span `no tools` before a comma, read as a negator of the claim after the comma. The turn has
        # no try.
        line = "The notice said: `no tools`, I cannot open a PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_masked_if_needed_before_a_semicolon_still_blocks(self):
        # Control: the base already blocks this line, so it is green here. It pins the verdict the fix must keep. The MCP
        # form of the same span, "MCP status: `if needed`; I cannot open a PR.", passed on 2aed48244 (red there, a
        # must-block), so the conditional read of masked text had a red case; this line is the control beside it.
        line = "The note said `if needed`; I cannot push."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_a_masked_connected_status_still_blocks(self):
        # Control: the same shape with `connected` in the span. Nothing negates the claim, so it blocks as no try.
        line = "MCP status: `connected`; I cannot open a PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pass_a_true_negation_of_a_push_claim_still_passes(self):
        # Control: "did not say" negates the telling, so the reply claims no act and the turn passes.
        out = self.stop([trg.human("push the branch"), trg.assistant_text("I did not say I cannot push.")])
        self.assert_passes(out, "a true negation of a push claim")

    # ---- follow-up 5: the notes that name it, the veil pins, the masked readers, the negator window and the subject

    def test_cc_red_an_emphasis_mark_in_a_status_span_hides_no_check(self):
        # Catches: the check search reading the marked text, so "**403**" after a colon named no check and a failed push
        # blocked its own claim. The control below sets the same status without marks, and it passes.
        line = "I **cannot** push: **403** Forbidden."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         landed_reply(line)])
        self.assert_passes(out, "a failed push, with its status set in emphasis marks")

    def test_cc_pass_the_same_status_without_emphasis_passes(self):
        # Control: the same line with no emphasis marks passes after the same failed push.
        line = "I cannot push: 403 Forbidden."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         landed_reply(line)])
        self.assert_passes(out, "the control: a failed push, with its status after a colon")

    def test_cc_red_a_token_dot_does_not_cut_the_reason_after_a_failed_push(self):
        # Catches: the reason scan cutting at the dot inside package.json, so the reason read only "package" and a failed
        # push whose reason holds a token dot blocked as naming no check.
        line = "I could not push because package.json is invalid."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         landed_reply(line)])
        self.assert_passes(out, "a failed push, with a reason that holds a token dot")

    def test_cc_red_open_as_an_adjective_in_a_prior_sentence_names_no_pr_act(self):
        # Catches: "open" read as the act pr-open in the sentence before a merge claim, so that sentence named no check of
        # the merge and a failed merge blocked its own claim.
        line = "PR 12 is open, but its checks failed. I cannot merge it."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_passes(out, "a failed merge, with its checks named in the sentence before the claim")

    def test_cc_pass_a_prior_sentence_with_checks_that_failed_passes(self):
        # Control: the same sentence with "has" in place of "is open, but" names the failed checks and passes.
        line = "PR 12 has checks that failed. I cannot merge it."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m"), landed_reply(line)])
        self.assert_passes(out, "the control: a failed merge, with its checks named in the sentence before the claim")

    def test_cc_red_a_reason_before_the_phrase_names_its_check(self):
        # Catches: a reason read only after the phrase, so a reason before it named no check and a failed push blocked.
        for line in ("Because the branch is protected, I cannot push.", "The branch is protected, so I cannot push."):
            with self.subTest(line=line):
                out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                                 landed_reply(line)])
                self.assert_passes(out, "a failed push, with its reason before the phrase: %s" % line)

    def test_cc_red_a_prior_sentence_writer_try_names_no_check(self):
        # Catches: the writer test missing from the prior-sentence check. "I tried; I cannot push." names no check in its own
        # sentence, so "I tried. I cannot push." names none either: the same try, in a prior sentence.
        for line in ("I tried. I cannot push.", "We tried. We cannot push."):
            with self.subTest(line=line):
                out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                                 landed_reply(line)])
                self.assert_blocked_for(out, NO_CHECK, line)

    def test_cc_pass_a_prior_sentence_that_says_the_push_failed_passes(self):
        # Control: a prior sentence that says the push failed names the check, so the line passes.
        line = "The push failed. I cannot push."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         landed_reply(line)])
        self.assert_passes(out, "the control: a failed push, named by its check word in a prior sentence")

    def test_cc_red_a_check_word_in_a_prior_sentence_names_its_check(self):
        # Catches: rejected, blocked and said missing from _CHECK_WORD, so a prior sentence that says the remote rejected
        # the push, the hook blocked it or the remote said a thing named no check, and a failed push blocked its claim.
        for line in ("The remote rejected the push. I cannot push.", "The hook blocked the push. I cannot push.",
                     "The remote said the ref is locked. I cannot push."):
            with self.subTest(line=line):
                out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                                 landed_reply(line)])
                self.assert_passes(out, "a failed push, named by a check word of a prior sentence: %s" % line)

    def test_cc_red_a_check_word_in_the_claims_clause_names_its_check(self):
        # Catches: the same three words in the claim's own clause, which the check reads only once _CHECK_WORD holds them.
        # The first line is the note's own example.
        for line in ("I tried and the remote rejected it, so I cannot push.",
                     "I tried and the hook blocked it, so I cannot push.",
                     "I tried and the remote said the ref is locked, so I cannot push."):
            with self.subTest(line=line):
                out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                                 landed_reply(line)])
                self.assert_passes(out, "a failed push, named by a check word in its clause: %s" % line)

    def test_cc_pass_a_failed_check_word_in_the_claims_clause_passes(self):
        # Control: "failed" is a check word already, so the same clause form passes.
        line = "I tried and the remote failed it, so I cannot push."
        out = self.stop([trg.human("push the branch"), *failed_bash("git push origin HEAD", "tu_p"),
                         landed_reply(line)])
        self.assert_passes(out, "the control: a failed push, named by the check word failed in its clause")

    def test_cc_red_an_until_in_a_code_span_is_no_dependency(self):
        # Catches: CANNOT_DEPENDENCY_RE reading the marked text, so "until" inside `until-ready` skipped a claim with no try.
        line = "I cannot push `until-ready`."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pass_an_until_in_plain_words_is_a_dependency(self):
        # Control: "until" in plain words waits on a dependency, so the claim is no claim.
        line = "I cannot push until ready."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_passes(out, "a claim that waits until a dependency is ready")

    def test_cc_red_a_rule_word_in_a_code_span_is_no_rule(self):
        # Catches: CANNOT_RULE_RE reading the marked text, so "rules" in `rules.md` made the sentence a rule statement, and a
        # claim with no try passed.
        line = "I cannot push, see `rules.md`."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pass_a_rule_word_in_plain_words_is_no_claim(self):
        # Control: "the rules" in plain words names a rule, so the sentence states the rule and is no claim.
        line = "I cannot push, see the rules."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_passes(out, "a sentence that names a rule in plain words")

    def test_cc_red_am_before_the_act_takes_no_negator_slot(self):
        # Catches: "am" taking a slot in the three-word negator window, so the "did not" before "say I am" fell out of it, and
        # the true negation of a telling blocked as a push claim with no try. The controls are the true negation "I did not
        # say I cannot push." (test_cc_pass_a_true_negation_of_a_push_claim_still_passes) and the claim "I am not authorized
        # to push." (test_cc_red_not_authorized_no_access_lack_permission_or_blocked_from_is_a_claim), which still blocks.
        line = "I did not say I am not authorized to push."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_passes(out, "a true negation of a push claim, with am before the act")

    def test_cc_red_this_session_with_a_be_verb_before_not_able_to_is_a_claim(self):
        # Catches: the own-subject check reading "this session" as a subject only where the phrase starts, so a be-verb
        # between it and "not able to" or "unable to" read as no claim. The spaced "isn't able to" blocks already, and is
        # pinned by test_cc_red_this_session_isnt_able_to_is_a_claim.
        for line in ("This session is not able to merge PR 12.", "This session is unable to merge PR 12."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_the_cloud_with_a_be_verb_before_unable_to_is_a_claim(self):
        # Catches: the same gap for "the cloud": a be-verb between it and "unable to" read as no claim with no try.
        line = "The cloud is unable to merge PR 12."
        out = self.stop([trg.human("merge PR 12"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pin_a_masked_if_needed_with_no_separator_still_blocks(self):
        # Pin of the veil in _claim (report_guard.py): an "if" in a code span before the claim conditions nothing. It blocks
        # at head. A mutant that reads the conditional from the unveiled text lets it through, so it goes red there.
        line = "The note said `if needed` I cannot push."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pin_a_masked_no_tools_with_no_separator_still_blocks(self):
        # Pin of the veil in _claim: a "no" in a code span negates nothing. It blocks at head. A mutant that reads the
        # negator from the unveiled text lets it through, so it goes red there.
        line = "The notice said `no tools` I cannot open a PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pin_a_negator_in_a_code_span_does_not_negate_the_claim(self):
        # Pin of the veil in _claim, read before the negation and conditional reads: a negator inside a code span negates
        # nothing. It blocks at head. A mutant that reads negated_near on the unveiled text lets it through, so it goes red.
        line = "MCP status: `not connected` I cannot open a PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pin_a_conditional_in_a_code_span_does_not_condition_the_claim(self):
        # Pin of the veil in _claim: a conditional inside a code span conditions nothing. It blocks at head. A mutant that
        # reads the conditional from the unveiled text lets it through, so it goes red there.
        line = "MCP status: `if needed` I cannot open a PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pin_a_two_word_code_span_keeps_its_two_words(self):
        # Pin of the veil's word count: a two-word span keeps two words, so the "not" before it stays outside the three-word
        # negator window. A mutant that blanks the span to spaces leaves no words, lets "not" into the window, and goes red.
        line = "MCP status: not `in use` I cannot open a PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)


if __name__ == "__main__":
    unittest.main()
