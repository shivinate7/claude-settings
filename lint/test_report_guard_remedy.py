#!/usr/bin/env python3
"""Owner-safe refusal reasons for report_guard.py (decision guard-remedy-not-to-owner).

A Stop refusal reason reaches the owner in chat. So each reason opens with one plain line that names its check,
cites the record guard-remedy-not-to-owner, and holds no order to the session. The detector for an order is
report_guard.session_wording, one home for the phrase list and the order rule. The steps for each check live in
that record, under a heading for the check, with at least one step line under each heading.

Each refusal path that has a fixture below runs through report_guard as a Stop hook. Not fixtured: the hand-off
guard's measured-premise-with-no-date and route-cite refusals, the departs guard's separator, empty-side,
placeholder and no-change misses, and the Unvetted "the check failed with <Exc>" text, which only an exception
inside the past-ruling check reaches. Each is one miss of a check that has a fixture. The transcript records and the
guard runner come from lint/test_report_guard.py. The repo fixtures and the model stub come from
hooks/test_call_judge.py. The triage records come from lint/test_report_guard_stalled.py.

Case 1a checks that no reason holds a session phrase or an order to the session. Case 1b checks the record cite.
Case 1c checks that the first sentence names the check. Case 2 checks that each path still refuses, and that a clean
report is not refused. Case 3 checks that the record holds a step heading for each check name that report_guard
passes to owner_line, and a step line under each heading. Controls pin session_wording on fact sentences, on plain
and mid-clause orders, on the phrase list, and on backtick spans: a span holds a fact, and an order outside a span
or one a span hides is still flagged. A judge reason that carries an order is checked at the Stop boundary:
the refusal still fires, the ruling id stays, and the order does not reach the owner word for word.

Run it as:

    python3 lint/test_report_guard_remedy.py -v
"""
import ast
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
import report_guard as RG  # noqa: E402  session_wording, the detector for an order to the session (one home)
import test_report_guard as trg  # noqa: E402  the transcript records, the guard runner and the run folder (one home)
import test_call_judge as tcj  # noqa: E402  the repo fixtures, the waiting-page url and the ruling (one home)
import test_report_guard_stalled as trs  # noqa: E402  the triage wake's build run and own record (one home)

CITE = "guard-remedy-not-to-owner"
RECORD = os.path.join(HERE, "..", "docs", "decisions", CITE + ".md")
FIXTURES = ("missing_report", "correction_tail", "done_format", "models", "unstarted", "unvetted",
            "past_ruling", "keys", "pick",
            "recovered", "departs_unlanded", "departs_landed", "answered", "mistake", "hand_off", "refusal",
            "lane", "pick_known_writer", "rewrite_stamp", "triage_hold", "unvetted_unreadable",
            "unvetted_cited", "rewrite_model", "rewrite_unstarted", "rewrite_answered", "rewrite_recovered",
            "recovered_no_source", "past_ruling_order", "refusal_two_tools")
FACT_SENTENCES = ("Pick guard: the page writer is session session_writer1 (decision guard-remedy-not-to-owner).",
                  "Names of the checks sit in the record. Keys are one option set per question.",
                  "The check reads the transcript, and a Done line holds one kind.")
# Plain orders: a sentence that opens with an order to the session.
ORDER_SENTENCES = ("Send it now: the report.", "Two questions; send the questions again.",
                   "Give the line. Keep it short.", "Do not write it again.", "Post only the corrected line.")
# Mid-clause orders: the order sits after a clause, so a check on the first word passes it. "so send it now" is also
# in the phrase list, so the phrase list catches it alone.
MID_CLAUSE_ORDERS = ("The question is old, so send it now.",
                     "The reply names four labels, drop a label that does not apply.",
                     "The ruling is old. You should send it.",
                     "The reply is not the report, so the reply must end with the report.")
# A sentence that only the phrase list catches: no order opens it, and PHRASE_PIN is in the phrase list.
PHRASE_ONLY = "The fix would reach the owner before the review."
PHRASE_PIN = "would reach the owner"
# The order the past-ruling judge wrote into its reason in the boundary case, which must not reach the owner.
JUDGE_ORDER = "Drop the question and send it again."
# A comma list of backticked words is a fact. Each span's word is in SESSION_IMPERATIVES, so the split at a comma must
# not read the span as an order.
TWO_TOOL_LIST = "The phrase list holds `add`, `send` and `post`."
# A comma ends a span, so the text after it is read as a unit: "Write` this session." opens with an order word.
COMMA_IN_SPAN_ORDER = "The classifier refused `Agent, Write` this session."
# Order controls: an order outside backticks is still flagged, and the exact unit comes back. In the lone-backtick text
# the first backtick has no close before the order; a strip that pairs it with the later backtick would hide the order.
ORDER_AFTER_SPAN = "The classifier refused `Agent`. Write the line. It also refused `Read`."
ORDER_AFTER_LONE_BACKTICK = "The `Agent tool was refused. Write the line. Keep `add` in view."
ORDER_UNIT = "Write the line."
# Each order below must be flagged. A backtick span names a thing and holds no order, so an order word or phrase inside
# a span, or an order after a comma that a lone backtick pairs across, is still an order.
SPAN_VERB_ORDER = "Next, `send` the report again."
SPAN_CAPITAL_ORDER = "Then `Write` the line."
SPAN_PHRASE_ORDER = "Please `send it again`."
LONE_BACKTICK_COMMA_ORDER = "The `Agent was refused, so write the line and keep `add` in view."
DOT_SPAN_ORDER = "Then `write.` the line."
# Controls, flagged on the old code too. A fix that let a span cross a newline would hide the order inside it.
NEWLINE_SPAN_BEFORE_ORDER = "The `Agent\ntool` was refused. Send the line."
NEWLINE_SPAN_ORDER = "The `Agent\nwrite` the line."
DOT_SPAN_BEFORE_ORDER = "The `v1.2` release is in. Send the line again."
# A connector before a span does not make the unit a list item: after "`Next`," the span is still an order word.
LIST_SO_SPAN_ORDER = "The reply lacks `Next`, so `add` it."
LIST_THEN_SPAN_ORDER = "The reply lacks `Next`, then `send` the report."
LIST_PLEASE_SPAN_ORDER = "The check read `Done`, please `send` it again."
# Controls. A unit after a list item that opens with a plain word is still read, so skipping every such unit fails here.
LIST_WORD_ORDER = "The classifier refused `Agent`, write the line."
# A span with a dot before its comma is no list item, so the verb unit after it is still read. This fails for a
# _SPAN_COMMA_END that drops the dot from its excluded marks.
DOT_LIST_VERB_ORDER = "The check read `a.b`, `add` it."
# A step line is a bullet or a numbered item. A section ends at the next ## or ### heading.
STEP_LINE = re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+\S")
SECTION_END = re.compile(r"(?m)^#{2,3} ")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def setUpModule():
    trg.setUpModule()  # the config isolation, the model stub and the run folder, as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()
    shutil.rmtree(tcj.ROOT, ignore_errors=True)  # the repo fixtures' run folder, which trg does not remove


def judge_answer(reason):
    """The past-ruling judge's answer that refuses with `reason`, as the model stub returns it."""
    return json.dumps({"ok": False, "reason": reason})


def owner_line_checks():
    """The check name of each owner_line call in report_guard.py, read from that module's own source. A name is a
    string literal or a module-level name bound to one. Any other argument reads as None."""
    with open(trg.REPORT_GUARD, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    consts = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            consts[node.targets[0].id] = node.value.value
    names = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "owner_line"
                and node.args):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.append(arg.value)
            elif isinstance(arg, ast.Name) and arg.id in consts:
                names.append(consts[arg.id])
            else:
                names.append(None)
    return names


def record_problems(record, names):
    """One problem per check name in `names` that has no `### <name>` heading in `record`, or whose section holds no
    step line. A section runs from its heading to the next ## or ### heading."""
    problems = []
    for name in sorted(set(names)):
        base = name.split(" (")[0].strip()
        head = re.search(r"(?m)^### " + re.escape(base) + r"\b", record)
        if not head:
            problems.append("no step heading for %r" % base)
            continue
        rest = record[head.end():]
        end = SECTION_END.search(rest)
        if not STEP_LINE.search(rest[:end.start()] if end else rest):
            problems.append("no step line under %r" % base)
    return problems


def landed(reply):
    """A turn that lands a commit, then the reply."""
    return [trg.human("do the task"), trg.tool_use_msg("Bash", {"command": "git commit -m x"}),
            trg.tool_result_msg(), trg.assistant_text(reply)]


def builder_turn(model, reply):
    """A turn that runs a builder on `model`, lands a commit, then the reply."""
    spawn = trg.tool_use_msg("Agent", {"subagent_type": "builder", "model": model, "prompt": "build it"})
    return [trg.human("do the task"), spawn, trg.tool_result_msg(),
            trg.tool_use_msg("Bash", {"command": "git commit -m x"}), trg.tool_result_msg(),
            trg.assistant_text(reply)]


def case(records, word, cwd, env=None, extra=None, prep=None):
    """One refusal path: the transcript `records`, the word the first sentence must hold, the repo `cwd`, the env and
    the hook fields (`extra`) the Stop needs, and `prep`, a case run first. A rewrite path refuses only after a
    missing-report refusal has left its marker, so its prep is that refusal."""
    return {"records": records, "word": word, "cwd": cwd, "env": env or {}, "extra": extra or {}, "prep": prep}


class RemedyReasons(trg.SameTurnWriter, unittest.TestCase):
    PAGE = tcj.PAGE_URL  # the waiting page tcj.make_repo names; the same-turn writer read cites it
    LANE_ID = trg.QuestionReachesPageTests.LANE_ID  # read by lane_record below, which takes self
    ARCHIVE = "mcp__claude-code-remote__archive_session"
    TWO_TOOLS = ("Agent", "Write")  # two refused tools; "Write" is an imperative word in SESSION_IMPERATIVES
    THREE_TOOLS = ("Agent", "Write", "Send")  # three refused tools; "Write" and "Send" open with an imperative word
    REFUSAL_SID = "remedy-refusal"
    PICK = ("> **Done** OTHER read the code\n> **Input Needed** Two ways:\n> A (my pick): fold the guard\n"
            "> B: add a second hook\n> **Next** wait")
    PROSE = "Nothing landed. The state is unchanged."
    HAND_OFF = ("Why yours: I can't push from here, since check_red_run showed the trailer needs the owner.\n"
                "> **Done** OTHER read the code\n> **Next** wait")

    def sent_to_writer(self):
        """The same-turn send to the page writer, so a question's own check stays quiet."""
        return [*self.writer_read(self.WRITER), *self.send(session_id=self.WRITER)]

    def unreadable_repo(self):
        """A repo whose decisions folder holds one record that is not UTF-8, so the past-ruling read is unreadable."""
        repo = tcj.make_repo("remedy-unreadable", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
        with open(os.path.join(repo, "docs", "decisions", "bad-encoding.md"), "wb") as handle:
            handle.write(b"# bad\n\n\xff\xfe\x00 not utf-8 \x81\n")
        return repo

    def refusal_repo_config(self, tools=(ARCHIVE,)):
        """A config folder whose refusals file holds one row per refused tool in `tools`, none of them raised by the
        reply."""
        cfg = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        path = os.path.join(cfg, "state", "refusals", self.REFUSAL_SID + ".jsonl")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            for tool in tools:
                handle.write(json.dumps({"ts": "2026-11-01T10:00:00-05:00", "tool_name": tool,
                                         "reason": "refused"}) + "\n")
        return cfg

    def rewrite(self, name, first, again, word, clean):
        """A missing-report refusal on `first`, then the rewrite `again` under the same session id, which the marker
        of that refusal reads. `first` and `again` hold the same turn up to the reply."""
        sid = "remedy-rewrite-" + name
        refusal = case(first, "report", clean, extra={"session_id": sid})
        return case(again, word, clean, extra={"session_id": sid, "stop_hook_active": True}, prep=refusal)

    def fixture(self, name):
        """The refusal path `name`, as a case dict. Every case names a cwd that tcj.make_repo built, so no check reads
        this worktree's own records."""
        clean = tcj.make_repo("remedy-clean")
        bare = tcj.make_repo("remedy-bare")
        decided = tcj.make_repo("remedy-decided", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
        shaped_relay = "> **Done** OTHER read the audit\n" + trg.RELAY + "\n> **Next** wait"
        lane_env = {"CLAUDE_CODE_REMOTE_SESSION_ID": trg.QuestionReachesPageTests.LANE_ENV}
        rw_done = "> **Done** BUILT abc123 (builder sonnet)"
        builders = {
            "missing_report": lambda: case(landed("Committed the change."), "report", clean),
            "correction_tail": lambda: case(landed("> **Done** BUILT abc123\n> **Next** ship it, see D12."),
                                            "gloss", clean),
            "done_format": lambda: case(landed("> **Done** BUILT\n> **Next** ship it"), "done", clean),
            "models": lambda: case(builder_turn("sonnet", "> **Done** BUILT abc123 (builder)\n"
                                                "> **Next** Unstarted: none"), "model", clean),
            "unstarted": lambda: case(builder_turn("sonnet", "> **Done** BUILT abc123 (builder sonnet)\n"
                                                   "> **Next** ship it"), "unstarted", clean),
            "unvetted": lambda: case([trg.human("decide"), *self.sent_to_writer(), trg.assistant_text(shaped_relay)],
                                     "unvetted", bare, env={"CJ_MODEL_FAIL": "1"}),
            "past_ruling": lambda: case([trg.human("decide"), *self.sent_to_writer(),
                                         trg.assistant_text(trg.RELAY)], "past-ruling", decided,
                                        env={"CJ_ANSWER": trg.REFUSE_APPS}),
            # The judge's reason carries an order. The refusal must still fire, with the ruling id, and no order.
            "past_ruling_order": lambda: case([trg.human("decide"), *self.sent_to_writer(),
                                               trg.assistant_text(trg.RELAY)], "past-ruling", decided,
                                              env={"CJ_ANSWER": judge_answer(
                                                  tcj.APPS_SLUG + " settles this. " + JUDGE_ORDER)}),
            "keys": lambda: case([trg.human("decide"), *self.sent_to_writer(), trg.assistant_text(trg.KEYS_SAME)],
                                 "key", bare),
            "pick": lambda: case([trg.human("decide"), trg.assistant_text(trg.RELAY)], "pick", bare),
            # Recovered: a landed report after a compaction that carries no Recovered line.
            "recovered": lambda: case(trg.CompactionCarryTests.compacted_turn(trg.REPORT_NO_LINE), "recovered", clean),
            # Recovered, the item names no source: the item names neither git, a page nor a digest.
            "recovered_no_source": lambda: case(trg.CompactionCarryTests.compacted_turn(
                trg.report_lines("Recovered: the ruling from chat", "Handoff gave: none")), "recovered", clean),
            # Departs from: a pick with no Departs from line. The writer send keeps the question check quiet.
            "departs_unlanded": lambda: case([trg.human("decide"), *self.sent_to_writer(),
                                              trg.assistant_text(self.PICK)], "departs", clean),
            "departs_landed": lambda: case([trg.human("decide"), *self.sent_to_writer(),
                                            trg.tool_use_msg("Bash", {"command": "git commit -m x"}),
                                            trg.tool_result_msg(), trg.assistant_text(self.PICK)],
                                           "departs", clean),
            "answered": lambda: case([trg.human("ask the owner"),
                                      trg.assistant_text("Answered: no permission rule can lift it.")],
                                     "answered", clean),
            "mistake": lambda: case(landed(trg.mg_report(trg.MG_INBOX)), "mistake", clean),
            "hand_off": lambda: case([trg.human("do the task"), trg.assistant_text(self.HAND_OFF)], "hand-off", clean),
            "refusal": lambda: case([trg.human("do the task"), trg.tool_use_msg(self.ARCHIVE), trg.tool_result_msg(),
                                     trg.assistant_text(self.PROSE)], "refusal", clean,
                                    env={"CLAUDE_CONFIG_DIR": self.refusal_repo_config()},
                                    extra={"session_id": self.REFUSAL_SID}),
            # Refusal of two tools: the reason lists both, and its list reads as a fact to the owner.
            "refusal_two_tools": lambda: case(
                [trg.human("do the task"), trg.tool_use_msg(self.TWO_TOOLS[0]), trg.tool_result_msg(),
                 trg.tool_use_msg(self.TWO_TOOLS[1], {"file_path": "notes.md"}), trg.tool_result_msg(),
                 trg.assistant_text(self.PROSE)], "refusal", clean,
                env={"CLAUDE_CONFIG_DIR": self.refusal_repo_config(self.TWO_TOOLS)},
                extra={"session_id": self.REFUSAL_SID}),
            # Lane: the lane's own get_session record, then a question with no send to the parent or the writer.
            "lane": lambda: case([*trg.QuestionReachesPageTests.lane_record(self), trg.human("decide"),
                                  trg.assistant_text(trg.RELAY)], "lane", bare, env=lane_env),
            # Pick with a known writer: the writer read names it, and nothing is sent to it.
            "pick_known_writer": lambda: case([trg.human("decide"), *self.writer_read(self.WRITER),
                                               trg.assistant_text(trg.RELAY)], "pick", bare),
            # Rewrite stamp: the record was last committed before the ruling the rewrite sentence names.
            "rewrite_stamp": lambda: self.rewrite_stamp_case(),
            "triage_hold": lambda: case([trg.human("wake"), *trs.own_record(trs.TRIAGE_ID, ["cs-build:triage"]),
                                         *trs.build_run(trs.stalled_lines(steps=["build-stalled-check"]), exit_code=1),
                                         trg.assistant_text(trs.WELL_FORMED)], "triage", clean,
                                        env={"CLAUDE_CODE_REMOTE_SESSION_ID": trs.TRIAGE_ENV},
                                        extra={"session_id": trs.OWNER_SESSION}),
            # Unvetted: a record the past-ruling read cannot decode, so the check cannot run.
            "unvetted_unreadable": lambda: case([trg.human("decide"), *self.sent_to_writer(),
                                                 trg.assistant_text(trg.RELAY)], "unvetted",
                                                self.unreadable_repo()),
            # Unvetted: the review cites a record that the check did not show it.
            "unvetted_cited": lambda: case([trg.human("decide"), *self.sent_to_writer(),
                                            trg.assistant_text(trg.RELAY)], "unvetted", decided,
                                           env={"CJ_ANSWER": json.dumps({"ok": False, "reason":
                                                "decisions/ghost-ruling: already decides this, 2026-10-28."})}),
            # Rewrite paths: the rewrite of a missing-report refusal is checked for the model, Unstarted, answered and
            # Recovered reasons.
            "rewrite_model": lambda: self.rewrite("model", builder_turn("sonnet", "All done."),
                                                  builder_turn("sonnet", "> **Done** BUILT abc123 (builder opus)\n"
                                                               "> **Next** Unstarted: none"), "model", clean),
            "rewrite_unstarted": lambda: self.rewrite("unstarted", builder_turn("sonnet", "All done."),
                                                      builder_turn("sonnet", rw_done + "\n> **Next** ship it"),
                                                      "unstarted", clean),
            "rewrite_answered": lambda: self.rewrite("answered", builder_turn("sonnet", "All done."),
                                                     builder_turn("sonnet", rw_done + "\n> **Next** Unstarted: none\n"
                                                                  "The owner answered it."), "answered", clean),
            "rewrite_recovered": lambda: self.rewrite("recovered",
                                                      trg.CompactionCarryTests.compacted_turn("All done."),
                                                      trg.CompactionCarryTests.compacted_turn(trg.REPORT_NO_LINE),
                                                      "recovered", clean),
        }
        return builders[name]()

    def rewrite_stamp_case(self):
        """A repo whose decision record was last committed before the ruling the reply says it was rewritten for."""
        repo = trg.DecisionRepo(tempfile.mkdtemp(dir=trg.RUN_FOLDER))
        repo.commit(trg.D_LAST_COMMIT, "ci-job-caps")
        repo.touch("2026-11-02T09:00:00Z")
        records = [trg.human("do the task"), trg.tool_use_msg("Bash", {"command": "git commit -m x"}),
                   trg.tool_result_msg(), trg.assistant_text(trg.done_reply(trg.RULING_SENTENCE))]
        return case(records, "rewrite", repo.path, env={"LOCAL_TIME_NOW": trg.NOW})

    def run_stop(self, c):
        """Run report_guard as the Stop hook on case `c`, and return what it printed (or {}). The remote id of the
        test's own session is removed first, so only the case's env names a remote session."""
        path = trg.write_transcript(c["records"], tempfile.mkdtemp(dir=trg.RUN_FOLDER))
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": c["cwd"]}
        hook.update(c["extra"])
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_REMOTE_SESSION_ID"}
        env.update(c["env"])
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0, "the guard exited with an error: %s" % run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else {}

    def refusal_for(self, name):
        """(reason, word) of the refusal path `name`. The path must refuse. Its prep, when it has one, runs first."""
        c = self.fixture(name)
        if c["prep"]:
            first = self.run_stop(c["prep"])
            self.assertEqual(first.get("decision"), "block",
                             "%s: the refusal before the rewrite is missing: %r" % (name, first))
        out = self.run_stop(c)
        self.assertEqual(out.get("decision"), "block", "%s: the path does not refuse: %r" % (name, out))
        return out["reason"], c["word"]

    def check_no_session_problem(self, name, reason):
        problem = RG.session_wording(reason)
        self.assertEqual(problem, "", "%s: 1a the reason holds a session phrase or an order to the session: %r"
                         % (name, problem))

    def check_cites_record(self, name, reason):
        self.assertIn(CITE, reason, "%s: 1b the reason does not cite %s" % (name, CITE))

    def check_first_sentence(self, name, reason, word):
        first = SENTENCE_END.split(reason, maxsplit=1)[0].lower()
        self.assertIn(word, first,
                      "%s: 1c the first sentence does not name the check (%r): %r" % (name, word, first))

    def test_2_clean_report_is_not_blocked(self):
        out = self.run_stop(case(landed(trg.GOOD_REPORT), "clean", tcj.make_repo("remedy-clean")))
        self.assertNotEqual(out.get("decision"), "block", "2 a clean report is refused: %r" % out)

    def assert_past_ruling_verdict(self, out, slug):
        """The refusal is the past-ruling verdict itself, not the Unvetted refusal, and it keeps the ruling id. The
        verdict is checked first, since the id and the order asserts read the same reason."""
        self.assertEqual(out.get("decision"), "block", "the past-ruling refusal did not fire: %r" % out)
        reason = out["reason"]
        self.assertTrue(reason.startswith("Past-ruling guard"),
                        "the refusal is not the past-ruling verdict: %r" % reason)
        self.assertNotIn("Unvetted", reason, "the refusal is the Unvetted one, not the verdict: %r" % reason)
        self.assertIn(slug, reason, "the reason lost the ruling id: %r" % reason)
        return reason

    def test_past_ruling_order_keeps_the_id_and_drops_the_order(self):
        reason = self.assert_past_ruling_verdict(self.run_stop(self.fixture("past_ruling_order")), tcj.APPS_SLUG)
        self.assertNotIn(JUDGE_ORDER, reason, "the judge's order reached the owner word for word: %r" % reason)
        self.assertEqual(RG.session_wording(reason), "", "the reason holds an order to the session: %r" % reason)

    def test_recovered_no_source_names_the_item_miss(self):
        reason, _ = self.refusal_for("recovered_no_source")
        self.assertTrue(reason.startswith("Recovered guard"), "the refusal is not the Recovered verdict: %r" % reason)
        self.assertIn("names no source", reason, "the refusal is not the no-source miss: %r" % reason)

    def test_mid_clause_orders_from_the_judge_do_not_reach_the_owner(self):
        decided = tcj.make_repo("remedy-decided-mid", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
        for order in MID_CLAUSE_ORDERS:
            with self.subTest(order=order):
                c = case([trg.human("decide"), *self.sent_to_writer(), trg.assistant_text(trg.RELAY)],
                         "past-ruling", decided,
                         env={"CJ_ANSWER": judge_answer(tcj.APPS_SLUG + " settles this. " + order)})
                reason = self.assert_past_ruling_verdict(self.run_stop(c), tcj.APPS_SLUG)
                self.assertNotIn(order, reason, "the judge's mid-clause order reached the owner: %r" % reason)
                self.assertEqual(RG.session_wording(reason), "", "the reason holds an order: %r" % reason)

    def test_1a_control_fact_sentences_are_not_flagged(self):
        for fact in FACT_SENTENCES:
            with self.subTest(fact=fact):
                self.assertEqual(RG.session_wording(fact), "", "control: a fact sentence is flagged: %r" % fact)

    def test_1a_control_orders_are_flagged(self):
        for order in ORDER_SENTENCES + MID_CLAUSE_ORDERS:
            with self.subTest(order=order):
                self.assertNotEqual(RG.session_wording(order), "", "control: an order is not flagged: %r" % order)

    def test_1a_control_phrase_list_is_pinned(self):
        found = RG.session_wording(PHRASE_ONLY)
        self.assertIn(PHRASE_PIN, found.lower(),
                      "control: the phrase list does not catch %r: %r" % (PHRASE_PIN, found))

    def test_1a_two_tool_refusal_reason_is_fact_only(self):
        # The reason report_guard emits for two refused tools. The scope is pinned first: the pair must sit in that
        # order, and "write" must still be an imperative word, or the case passes for the wrong reason.
        reason = RG.refusal_reason(list(self.TWO_TOOLS))
        self.assertIn("`Agent`, `Write`", reason, "1a scope: the two-tool list is not in the reason: %r" % reason)
        self.assertIn("write", RG.SESSION_IMPERATIVES, "1a scope: 'write' is no longer an imperative word")
        problem = RG.session_wording(reason)
        self.assertEqual(problem, "", "1a the two-tool refusal reason reads as an order to the session: %r" % problem)

    def test_1a_backtick_word_list_is_fact_only(self):
        problem = RG.session_wording(TWO_TOOL_LIST)
        self.assertEqual(problem, "", "1a a comma list of words in backticks reads as an order: %r" % problem)

    def test_1a_control_comma_inside_span_order_is_flagged(self):
        self.assert_order_flagged(COMMA_IN_SPAN_ORDER, "a comma inside a backtick span hides the order after it")

    def test_1a_control_order_after_span_is_flagged_exactly(self):
        found = RG.session_wording(ORDER_AFTER_SPAN)
        self.assertEqual(found, ORDER_UNIT, "control: the order outside a span is not flagged as its own unit: %r"
                         % found)

    def test_1a_control_order_after_lone_backtick_is_flagged_exactly(self):
        found = RG.session_wording(ORDER_AFTER_LONE_BACKTICK)
        self.assertEqual(found, ORDER_UNIT, "control: an order after a lone backtick is hidden or cut: %r" % found)

    def assert_order_flagged(self, text, cause):
        """session_wording flags `text`. The scope comes first: the same words with no backticks are an order, so a miss
        on `text` is the span's doing, not the detector's."""
        self.assertNotEqual(RG.session_wording(text.replace("`", "")), "",
                            "1a scope: the words with no backticks are not an order: %r" % text)
        self.assertNotEqual(RG.session_wording(text), "", "1a %s: %r" % (cause, text))

    def test_1a_order_verb_in_span_is_flagged(self):
        self.assert_order_flagged(SPAN_VERB_ORDER, "an order word inside a backtick span is not flagged")

    def test_1a_order_capital_verb_in_span_is_flagged(self):
        self.assert_order_flagged(SPAN_CAPITAL_ORDER, "an order word inside a backtick span is not flagged")

    def test_1a_order_phrase_in_span_is_flagged(self):
        self.assert_order_flagged(SPAN_PHRASE_ORDER, "an order phrase inside a backtick span is not flagged")

    def test_1a_order_after_comma_past_lone_backtick_is_flagged(self):
        self.assert_order_flagged(LONE_BACKTICK_COMMA_ORDER, "a lone backtick pairs across a comma and hides the order")

    def test_1a_order_inside_dot_span_is_flagged(self):
        self.assert_order_flagged(DOT_SPAN_ORDER, "an order inside a backtick span with a dot is not flagged")

    def test_1a_control_newline_span_before_order_is_flagged(self):
        self.assert_order_flagged(NEWLINE_SPAN_BEFORE_ORDER,
                                  "control: an order after a span with a newline is not flagged")

    def test_1a_control_order_inside_newline_span_is_flagged(self):
        self.assert_order_flagged(NEWLINE_SPAN_ORDER, "control: an order inside a span with a newline is not flagged")

    def test_1a_control_dot_span_before_order_is_flagged(self):
        self.assert_order_flagged(DOT_SPAN_BEFORE_ORDER, "control: an order after a span with a dot is not flagged")

    def test_1a_order_span_after_list_so_is_flagged(self):
        self.assert_order_flagged(LIST_SO_SPAN_ORDER,
                                  "an order span after a list item and 'so' is skipped as a list item")

    def test_1a_order_span_after_list_then_is_flagged(self):
        self.assert_order_flagged(LIST_THEN_SPAN_ORDER,
                                  "an order span after a list item and 'then' is skipped as a list item")

    def test_1a_order_span_after_list_please_is_flagged(self):
        self.assert_order_flagged(LIST_PLEASE_SPAN_ORDER,
                                  "an order span after a list item and 'please' is skipped as a list item")

    def test_1a_control_word_after_list_is_flagged(self):
        self.assert_order_flagged(LIST_WORD_ORDER, "control: a word order after a list item is skipped")

    def test_1a_control_verb_after_dot_span_list_is_flagged(self):
        self.assert_order_flagged(DOT_LIST_VERB_ORDER, "control: a verb unit after a dotted span list item is skipped")

    def test_1a_three_tool_refusal_reason_is_fact_only(self):
        # Three refused tools, two of them opening with an imperative word. The scope is pinned first: the three names
        # must sit in that order, and "send" must still be an imperative word, or the case passes for the wrong reason.
        reason = RG.refusal_reason(list(self.THREE_TOOLS))
        self.assertIn("`Agent`, `Write`, `Send`", reason,
                      "1a scope: the three-tool list is not in the reason: %r" % reason)
        self.assertIn("send", RG.SESSION_IMPERATIVES, "1a scope: 'send' is no longer an imperative word")
        problem = RG.session_wording(reason)
        self.assertEqual(problem, "", "1a the three-tool refusal reason reads as an order to the session: %r" % problem)

    def test_3_record_has_a_step_heading_and_step_line_for_each_owner_line_check(self):
        # The names come from report_guard.py's own source, the one place each owner_line call is written.
        names = owner_line_checks()
        self.assertTrue(names, "report_guard passes no check name to owner_line")
        self.assertNotIn(None, names, "a check name is neither a literal nor a module constant: it cannot be read")
        self.assertTrue(os.path.exists(RECORD), "the decision record is missing: %s" % RECORD)
        with open(RECORD, encoding="utf-8") as handle:
            record = handle.read()
        for name in sorted(set(names)):
            with self.subTest(check=name):
                self.assertEqual(record_problems(record, [name]), [],
                                 "3 the record holds no step heading and step line for the check %r" % name)

    def test_3_record_holds_the_correction_step_in_shared_tails(self):
        # The refusals hold no correction text, so the one step that asks for the corrected lines lives in the record's
        # shared tails. The section must exist first; the two phrases are then read inside it.
        with open(RECORD, encoding="utf-8") as handle:
            record = handle.read()
        scope = re.search(r"(?m)^## Shared tails\n", record)
        self.assertTrue(scope, "3 the record has no Shared tails section")
        end = SECTION_END.search(record, scope.end())
        tails = record[scope.end():end.start() if end else len(record)].lower()
        for phrase in trg.CORRECTION_STEP:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, tails, "3 the record's Shared tails hold no correction step with %r" % phrase)

    def test_3_section_with_no_step_line_is_flagged(self):
        # A section that holds its heading and prose, and no step, is a problem. A section with a step is not.
        emptied = "### Recovered guard\n\nText: `RECOVERED_REASON`.\n\n### Pick guard\n\n- Pick the one.\n"
        self.assertEqual(record_problems(emptied, ["Recovered guard", "Pick guard"]),
                         ["no step line under 'Recovered guard'"])
        self.assertEqual(record_problems(emptied, ["Unvetted guard"]), ["no step heading for 'Unvetted guard'"])


def _case_1a(name):
    def test(self):
        reason, _ = self.refusal_for(name)
        self.check_no_session_problem(name, reason)
    return test


def _case_1b(name):
    def test(self):
        reason, _ = self.refusal_for(name)
        self.check_cites_record(name, reason)
    return test


def _case_1c(name):
    def test(self):
        reason, word = self.refusal_for(name)
        self.check_first_sentence(name, reason, word)
    return test


def _case_2(name):
    def test(self):
        self.refusal_for(name)  # asserts the refusal itself
    return test


for _name in FIXTURES:
    setattr(RemedyReasons, "test_1a_%s_no_session_phrase" % _name, _case_1a(_name))
    setattr(RemedyReasons, "test_1b_%s_cites_record" % _name, _case_1b(_name))
    setattr(RemedyReasons, "test_1c_%s_first_sentence_names_check" % _name, _case_1c(_name))
    setattr(RemedyReasons, "test_2_%s_still_blocks" % _name, _case_2(_name))


# ------------------------------------------------------------------ R39: the relayed question and the record's steps
#
# R39 in docs/plans/restart-plan.md. A relayed question (report_guard.past_ruling_problem) judges item 8 with call_judge's
# text, the one home. The owner-facing refusal holds no steps (decision guard-remedy-not-to-owner, session_wording), so the
# session's how-to to challenge is the Past-ruling step section of that record: its steps name a challenge that brings a
# new fact, call the other parts optional, and no step tells the session to withdraw or drop the question. The shape checks
# below copy those of hooks/test_call_judge.py new_shape_checks, because this file's red run imports the test_call_judge.py
# of the old commit, where a new name would crash the run instead of failing a check.

CHALLENGE_ASKED = (
    tcj.APPS_GOAL + "\n"
    + ("Challenge to %s: its sentence keeps the apps' access as is. The audit counts 14 apps now, not the 9 it was "
       "written on, so the outcome it protected needs a fresh measure. Proposed fix: remove the 5 unused apps."
       % tcj.APPS_SLUG))
PAST_RULING_HEAD = re.compile(r"(?m)^### Past-ruling guard\b")


def challenge_shape(text):
    """(label, passed) for the shape of a challenge in `text`, as hooks/test_call_judge.py new_shape_checks reads it: a
    challenge that names the record and brings a new fact passes, the other parts are optional, and no step requires the
    four parts."""
    t = text.lower()
    sentences = [s for s in re.split(r"[.\n]", t) if s.strip()]
    return [
        ("names the record and brings a new fact",
         any("challenge" in s and "record" in s and "new fact" in s for s in sentences)),
        ("calls the outcome and the fix optional",
         any(re.search(r"\b(optional|never required|not required)\b", s) and ("outcome" in s or "fix" in s)
             for s in sentences)),
        ("requires no step to give the four parts", re.search(r"\bthose parts\b|\bfour\b", t) is None),
    ]


def past_ruling_steps():
    """The text of the record's Past-ruling section, from its heading to the next ## or ### heading, or None."""
    with open(RECORD, encoding="utf-8") as handle:
        record = handle.read()
    head = PAST_RULING_HEAD.search(record)
    if not head:
        return None
    rest = record[head.end():]
    end = SECTION_END.search(rest)
    return rest[:end.start()] if end else rest


class RelayedChallenge(unittest.TestCase):
    """A relayed question's item 8 is call_judge's text, and the record's Past-ruling steps carry the challenge."""

    def relayed_prompt(self, asked):
        """(verdict, prompt): what report_guard.past_ruling_problem returns for `asked`, and the prompt it sends. The model
        call is a stub that answers ok, so the prompt is read back and no model runs."""
        import decision_watch
        sent = []

        def stub(prompt, **_):
            sent.append(prompt)
            return {"ok": True}, ""

        real = decision_watch.invoke_model
        decision_watch.invoke_model = stub
        try:
            verdict = RG.past_ruling_problem(asked, tcj.DECISIONS_REPO)
        finally:
            decision_watch.invoke_model = real
        return verdict, (sent[0] if sent else "")

    def test_relayed_question_sends_call_judge_item_8(self):
        import call_judge
        _, prompt = self.relayed_prompt(CHALLENGE_ASKED)
        self.assertNotEqual(prompt, "", "the relayed question made no model call")
        self.assertIn("8. " + call_judge.PAST_RULING_ITEM, prompt,
                      "the relayed prompt does not carry call_judge's item 8")

    def test_item_8_names_a_challenge_that_passes(self):
        import call_judge
        self.assertIn("challenge", call_judge.PAST_RULING_ITEM.lower(), "item 8 names no challenge that passes")

    def test_past_ruling_steps_name_how_to_challenge(self):
        section = past_ruling_steps()
        self.assertIsNotNone(section, "the record has no Past-ruling step section")
        self.assertIn("challenge", section.lower(), "the Past-ruling steps name no way to challenge a ruling")
        for label, ok in challenge_shape(section):
            with self.subTest(element=label):
                self.assertTrue(ok, "the Past-ruling steps do not say: %s" % label)

    def test_past_ruling_steps_never_say_withdraw(self):
        section = past_ruling_steps()
        self.assertIsNotNone(section, "the record has no Past-ruling step section")
        bad = [line for line in section.splitlines()
               if STEP_LINE.search(line) and any(p in line.lower() for p in ("withdraw", "drop the question"))]
        self.assertEqual(bad, [], "a Past-ruling step tells the session to withdraw the question: %r" % bad)


QUESTION_FORM_RECORD = os.path.join(HERE, "..", "docs", "decisions", "question-form.md")


class ChallengeRecord(unittest.TestCase):
    """The question-form record's item 8 line says a challenge passes on the record and a new fact, not on four parts."""

    def item_8_line(self):
        with open(QUESTION_FORM_RECORD, encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if "eighth item" in line]
        return lines[0] if lines else ""

    def test_item_8_line_names_a_challenge_that_brings_a_new_fact(self):
        line = self.item_8_line().lower()
        self.assertTrue(line, "the question-form record has no item 8 line")
        names = re.search(r"\bnames? the record\b|\bnaming the record\b", line)
        brings = re.search(r"\bbrings? a new fact\b|\bbringing a new fact\b", line)
        self.assertTrue(names and brings,
                        "the item 8 line does not say a challenge names the record and brings a new fact: %r" % line[:200])

    def test_item_8_line_drops_the_four_part_bar(self):
        line = self.item_8_line()
        self.assertTrue(line, "the question-form record has no item 8 line")
        self.assertNotIn("four parts", line.lower(), "the item 8 line still requires four parts")
        self.assertNotIn("A new fact alone is not a pass", line,
                         "the item 8 line still says a new fact alone is not a pass")


if __name__ == "__main__":
    unittest.main()
