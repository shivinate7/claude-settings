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

HEAD = "Cannot-claim guard (rule output-never-hand-off-doable-step)"
NO_TRY = "no failed try"
NO_CHECK = "names no check"
OPEN_PR = "mcp__github__create_pull_request"
REFUSED_ROW_ID = "r-archive"
ROW_REFUSED = hook_base.route_row(REFUSED_ROW_ID, "archive_session", "refused", surface="local")
# Words a remedy must not name: the act a refusal is about (git-remedy-never-names-target).
ACT_WORDS = re.compile(r"\bPR\b|pull request|\bopen\b|\bpush\b|\bmerge\b|\bgit\b|\bgh\b|mcp__", re.I)


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

    def stop(self, records, active=False, refused=(), rows=()):
        """The Stop decision for `records`, or None. The route-rows file and the refusals file sit in this case's
        folder, and the surface is pinned to local so a row's outcome reads on it."""
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
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=hook_base.surface_env(env, "local"))
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

    # ---- red: each fails on the unchanged code, where no check exists. One case per method, so the red count is clean.

    def test_cc_red_notice_is_no_try_for_an_unlanded_claim(self):
        # Catches: the incident. A connect-failure notice and a failed grep were read as tries of the PR, so the line
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
        # Re-pointed from test_cc_red_other_act_with_no_failure_has_no_try by the narrowing ruling (23:50 CST Nov 7,
        # decision guard-that-cries-wolf-is-spent): a rebase is outside the act table, so the line is no claim whether or
        # not a call failed. The call here succeeded, and the line passes.
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
        # message (the lane ruling on the window).
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
        # The text carries the failure (no error flag), so the HTTP 4xx reading is the one that counts.
        line = "I cannot open the PR: `curl` returned HTTP 403."
        out = self.stop([trg.human("open a PR"),
                         *failed_bash("curl -s -X POST https://api.github.com/repos/o/r/pulls -d @body.json",
                                      "tu_c", error=False),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a curl to the pulls route, named with its 403")

    def test_cc_green_other_act_with_a_failure_and_its_check_passes(self):
        # Re-pointed by the narrowing ruling (23:50 CST Nov 7, decision guard-that-cries-wolf-is-spent): a rebase is outside
        # the act table, so the line passes with or without a failure. The two failure forms still pass, and the failure
        # is no longer what clears the line.
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
        # own call. The spawn names no subagent type, and the turn lands on nothing, so only the relay can back the line.
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
        # The incident turn again, with a reply that claims nothing. The check stays quiet.
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         *failed_bash("grep -r pulls ci/", "tu_g"),
                         trg.assistant_text("Opening the PR from the MCP route next.")])
        self.assert_passes(out, "the incident turn with a reply that claims nothing")

    # ---- review round 1: each probe line below is a bypass the review found, or a false alarm. A red fails on the
    # unchanged guard. The green controls keep a line the check must still leave alone.

    def test_cc_red_other_act_is_backed_only_by_a_try_sharing_a_word(self):
        # Re-pointed by the narrowing ruling (23:50 CST Nov 7, decision guard-that-cries-wolf-is-spent): "reach GitHub" is
        # the github-reach row, so only a failed GitHub route backs it. The failed grep is no GitHub route, and the notice
        # is no try, so the claim still has no try. The routes that do back it are in the github-reach cases below.
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
        # flag, an exit code above zero, or an HTTP 4xx or 5xx status. A loose word in the output is none of these.
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

    # ---- round 3 (lane ruling, 23:50 CST Nov 7, decision guard-that-cries-wolf-is-spent: narrow the check to the act
    # table). A claim counts only when its act is a table act: pr-open, pr-merge, push, pr-edit or github-reach. A claim
    # of any other act passes. Each probe line is a subTest, so a red names the line.

    def test_cc_red_r1_f1_false_alarms_pass(self):
        # R1, F1: a claim of an act outside the table is no claim. The last line's subject is a third party (R2). None of
        # the lines has a try in its turn, so only the narrowing can clear them.
        lines = ("I couldn't find any callers of that function.", "I can't run the tests here; `pytest` exited 2.",
                 "The read cannot stop the merge.", "I can't open the file in the editor.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("check the callers"), trg.assistant_text(line)])
                self.assert_passes(out, "a round 1 false alarm: %r" % line)

    def test_cc_red_r1_f2_failed_gh_api_backs_a_github_reach_claim(self):
        # R1, F2: a failed gh call is a GitHub route, so it is a try of the github-reach act. The line names the call.
        line = "I can't reach GitHub from here: `gh api` returned 403."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("gh api repos/o/r", "tu_a"),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a failed gh api is a GitHub route try")

    def test_cc_red_r1_f2_failed_ls_remote_backs_a_github_reach_claim(self):
        # R1, F2: git ls-remote is a GitHub route when it reads the remote, so a failed one backs the claim.
        line = "I can't reach GitHub from here: `git ls-remote` failed."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("git ls-remote origin", "tu_l"),
                         trg.assistant_text(line)])
        self.assert_passes(out, "a failed git ls-remote is a GitHub route try")

    def test_cc_red_r1_f2_a_grep_sharing_a_word_backs_no_github_reach_claim(self):
        # R1, F2, the round 1 bypass again: a grep whose command holds the word github is no GitHub route, so it backs
        # nothing. The claim names the grep, so the no-try variant is the one that fires.
        line = "I can't reach GitHub from here: `grep -r github ci/` returned 1."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("grep -r github ci/", "tu_g"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_r1_f2_access_the_github_api_needs_a_github_route_try(self):
        # R1, F2: "access the GitHub API" is the github-reach row. The failed grep shares the word github and is no route.
        line = "I can't access the GitHub API from here."
        out = self.stop([trg.human("reach GitHub"), *failed_bash("grep -r github ci/", "tu_g"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r1_f2_reach_github_with_only_a_notice_blocks(self):
        # R1, F2, a control: a connect notice is no try, so the github-reach claim still has none.
        line = "I can't reach GitHub from here."
        out = self.stop([trg.human("reach GitHub"), notice("github: failed to connect"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_r2_a_draft_pr_subject_is_third_party(self):
        # R2: the subject just before the phrase must be first person, or the phrase opens its clause. "A draft PR" is
        # neither, so the line is no claim about this session.
        for line in ("The draft PR cannot be merged yet.", "A draft PR can't be merged here."):
            with self.subTest(line=line):
                out = self.stop([trg.human("merge the draft"), trg.assistant_text(line)])
                self.assert_passes(out, "a draft PR as the subject: %r" % line)

    def test_cc_green_r2_first_person_subjects_block(self):
        # R2, a control: the cloud and this session are first person, so the claim blocks.
        for line in ("The cloud cannot open the PR.", "This session can't open the PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r2_a_builder_or_the_session_passes(self):
        # R2, a control: a builder is a third party, and "the session" stays third party (only "this session" is first).
        for line in ("The builder cannot open the PR.", "The session cannot open the PR."):
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a third-party subject: %r" % line)

    def test_cc_red_r3_a_later_success_on_another_target_does_not_cancel(self):
        # R3: a later success cancels an earlier failure only for the same act, the same target and the same verb. Merge
        # 13 is another PR, so the failed merge of 12 still backs the claim about 12.
        line = "I cannot merge PR 12: `gh pr merge 12` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m1"),
                         *ok_bash("gh pr merge 13", "tu_m2"), landed_reply(line)])
        self.assert_passes(out, "a success on PR 13 against a failure on PR 12")

    def test_cc_red_r3_a_later_success_with_another_verb_does_not_cancel(self):
        # R3: a comment on PR 12 is the same act as a close of PR 12 (pr-edit), but another verb, so it cancels nothing.
        line = "I cannot close PR 12: `gh pr close 12` failed."
        out = self.stop([trg.human("close PR 12"), *failed_bash("gh pr close 12", "tu_c1"),
                         *ok_bash("gh pr comment 12 --body done", "tu_c2"), landed_reply(line)])
        self.assert_passes(out, "a comment on PR 12 against a failed close of PR 12")

    def test_cc_red_r3_a_dry_run_success_does_not_cancel(self):
        # R3: a call with --dry-run never cancels a failure, so a dry run that succeeded leaves the failed merge standing.
        line = "I cannot merge PR 12: `gh pr merge 12` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m1"),
                         *ok_bash("gh pr merge 12 --dry-run", "tu_m2"), landed_reply(line)])
        self.assert_passes(out, "a dry run that succeeded against a failed merge")

    def test_cc_red_r3_a_failed_dry_run_is_no_try(self):
        # R3: a call with --dry-run never counts as a try either, so a failed dry run backs no claim of the merge.
        line = "I cannot merge PR 12: `gh pr merge 12 --dry-run` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12 --dry-run", "tu_d"),
                         landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r3_a_same_target_and_verb_success_cancels(self):
        # R3, a control: the same act, target and verb, succeeding later, still cancels the failure.
        line = "I cannot merge PR 12: `gh pr merge 12` failed."
        out = self.stop([trg.human("merge PR 12"), *failed_bash("gh pr merge 12", "tu_m1"),
                         *ok_bash("gh pr merge 12", "tu_m2"), landed_reply(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_r4_rule_forms_and_the_cannot_suite_pass(self):
        # R4: a sentence that names a rule or a decision is the rule's text, not the session's claim. "Cannot" directly
        # before a noun used as a modifier (the cannot suite, the cannot cases) is no claim.
        lines = ("Rule: I cannot open the PR here.", "Per the decision, I cannot open the PR.",
                 "Decision: pr-open-needs-grant (I cannot open the PR).", "The cannot suite passes.",
                 "The cannot cases pass.")
        for line in lines:
            with self.subTest(line=line):
                out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
                self.assert_passes(out, "a rule form or a modifier: %r" % line)

    def test_cc_red_r5_a_cloud_session_after_a_skipped_phrase_blocks(self):
        # R5: each phrase of a line is judged. The first phrase's subject is a third party. The second names the cloud
        # session, which is first person (R2), so the line blocks on the second.
        line = "The guard can't see the box, and the cloud session cannot open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_r5_the_cloud_session_cannot_open_the_pr_blocks(self):
        # R5: "the cloud session" is first person, so the line is a claim about this session.
        line = "The cloud session cannot open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_r5_two_phrases_both_judged_block(self):
        # R5, a control: a third-party first phrase does not clear the line, because the second phrase is a claim.
        line = "The read cannot stop the merge, and I can't open the PR."
        out = self.stop([trg.human("open a PR"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_pin_r7_an_unreadable_refusals_file_fails_open_with_an_unknown_note(self):
        # R7: a refusals file that cannot be read skips the check (fail open), and the Stop run says so on stderr as
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

    # ---- a claim after a bold report label. "**Input Needed** Could not open the PR" is the incident's own hand-off
    # form. The label is no subject: the clause after it opens, so the phrase has an empty subject and is a claim.

    def test_cc_red_a_claim_after_a_bold_input_needed_label_has_no_try(self):
        # Catches: the bold label read as the phrase's subject, so the line passed as no claim. The only evidence is a
        # connect notice, which is no try.
        line = "**Input Needed** Could not open the PR."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_a_claim_in_an_input_needed_report_line_has_no_try(self):
        # The same claim as the Input Needed line of a report, where the incident's hand-off form sits.
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

    # ---- the follow-up to the claim-backing debts: the gate-reason debt, the script-try debt, and the notes on check
    # words, the api.github.com dot, the missed act words and the semicolon scan. A red line is a claim the check must
    # read. A control is a line its fix must leave as it is, and each control names whether it already passes.

    def test_cc_red_gate_reason_because_ci_is_no_claim(self):
        # Catches: a claim whose clause carries a gate (because CI) read as a claim with no try. A gate is a true reason,
        # so the line is no hand-off. The turn holds no try, so only the gate skip can clear it.
        line = "I can't merge the PR because CI is red."
        out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
        self.assert_passes(out, "a claim whose clause carries a gate (because CI)")

    def test_cc_red_gate_reason_while_the_batch_run_is_no_claim(self):
        # Catches: a claim whose clause carries a gate (while the batch run) read as a claim with no try.
        line = "I cannot merge it while the batch run is in progress."
        out = self.stop([trg.human("merge the PR"), trg.assistant_text(line)])
        self.assert_passes(out, "a claim whose clause carries a gate (while the batch run)")

    def test_cc_red_gate_reason_rule_id_after_the_act_is_no_claim(self):
        # Catches: a claim that names its hyphenated rule id in parentheses after the act, read as a claim with no try.
        line = "I can't push to main (git-main-only-by-pr)."
        out = self.stop([trg.human("push to main"), trg.assistant_text(line)])
        self.assert_passes(out, "a claim that names its rule id after the act")

    def test_cc_green_connect_failure_because_clause_still_blocks(self):
        # Control, already green: a connect failure is no gate, so the because clause does not skip the claim. The
        # notice is no try, so the line blocks as no try.
        line = "I can't open the PR because the MCP server failed to connect."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_could_not_open_with_only_a_notice_still_blocks(self):
        # Control, already green: a bare claim whose only evidence is a notice. The notice is no try, so it blocks.
        line = "I could not open the PR."
        out = self.stop([trg.human("open a PR for the branch"), notice("github: failed to connect"),
                         trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_plain_cannot_merge_with_no_try_or_cite_still_blocks(self):
        # Control, already green, for the gate-reason debt's retire line: with no gate, no try and no cite, it blocks.
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
        # Control, already green: a failed script whose name holds no act word backs no act, so the claim blocks.
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
        # Control, already green: a dot inside github.com is also no clause end, and the claim still blocks as no try.
        line = "I can't reach github.com from here."
        out = self.stop([trg.human("reach GitHub"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_red_git_push_with_a_command_word_before_the_verb_is_a_claim(self):
        # Catches: "git" between the phrase and the verb, so "I can't git push" reads as no push claim.
        line = "I can't git push the branch."
        out = self.stop([trg.human("push the branch"), trg.assistant_text(line)])
        self.assert_blocked_for(out, NO_TRY, line)

    def test_cc_green_git_push_claim_with_its_failed_try_and_check_passes(self):
        # Control, already green: the same claim backed by a failed git push, named. The fix must keep the try and check.
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
        # the no-try variant. It reads no clock, so it is green on the old code and must stay green after a fix.
        run = self.reply_run(" ".join(["I can't open the PR;"] * 7800) + ".", timeout=120)
        out = json.loads(run.stdout) if run.stdout.strip() else None
        self.assertIsNotNone(out, "no block came for the 160 KB sentence")
        self.assertEqual(out.get("decision"), "block", "the 160 KB sentence was not blocked")
        self.assertIn(HEAD, out.get("reason", ""), "the block for the 160 KB sentence is not the cannot-claim guard")
        self.assertIn(NO_TRY, out.get("reason", ""), "the 160 KB sentence has the wrong variant")


if __name__ == "__main__":
    unittest.main()
