#!/usr/bin/env python3
"""Owner-safe block reasons for report_guard.py (decision guard-remedy-not-to-owner).

A Stop block reason reaches the owner in chat. So each reason opens with one plain line that names its check,
cites the record guard-remedy-not-to-owner, and holds no order to the session. The steps for each check live in
that record, under a heading for the check.

Each block path that has a fixture below runs through report_guard as a Stop hook. Not fixtured: the hand-off
guard's measured-premise-with-no-date and route-cite refusals, and the departs guard's separator, empty-side,
placeholder and no-change misses. Each is one miss of a check that has a fixture. The transcript records and the
guard runner come from lint/test_report_guard.py. The repo fixtures and the model stub come from
hooks/test_call_judge.py. The triage records come from lint/test_report_guard_stalled.py.

Case 1a checks that no reason holds a session phrase or a sentence that opens with an order to the session. Case
1b checks the record cite. Case 1c checks that the first sentence names the check. Case 2 checks that each path
still blocks, and that a clean report is not blocked. Case 3 checks that the record holds a step heading for each
check name that report_guard passes to owner_line. Two controls pin the 1a helper on fact sentences and on orders.

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
import test_report_guard as trg  # noqa: E402  the transcript records, the guard runner and the run folder (one home)
import test_call_judge as tcj  # noqa: E402  the repo fixtures, the waiting-page url and the ruling (one home)
import test_report_guard_stalled as trs  # noqa: E402  the triage wake's build run and own record (one home)

CITE = "guard-remedy-not-to-owner"
RECORD = os.path.join(HERE, "..", "docs", "decisions", CITE + ".md")
# Phrases a block reason must not carry to the owner, matched case-insensitively. The last two reached the owner
# in main's pick and keys reasons, and the order check below does not catch them when they sit mid-sentence.
SESSION_PHRASES = (
    "send it again", "send the report", "post only", "never send", "add the line", "remedy:",
    "do not write it again", "keep the reply", "would reach the owner", "as the next thing you write",
    "send it now", "send the questions again",
)
# A unit (a sentence, a clause after ";" or ":", or a line) that opens with one of these words is an order to the
# session. "Pick" is left out on purpose: "Pick guard" is the check name of an owner line.
IMPERATIVES = frozenset((
    "add", "send", "post", "keep", "write", "drop", "give", "name", "move", "run", "never", "do", "don't", "resend",
    "rewrite", "mark", "resume", "pause", "fix", "ship", "wait", "reply", "put", "cite", "check", "answer", "close",
    "open", "update", "remove", "include", "set", "make", "stop", "let", "tell", "ask", "see", "read", "dispose",
))
UNIT_END = re.compile(r"(?<=[.!?;:])\s+|\n+")
WORD = re.compile(r"[a-z][a-z'-]*")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
FIXTURES = ("missing_report", "correction_tail", "done_format", "models", "unstarted", "unvetted",
            "past_ruling", "keys", "pick",
            "recovered", "departs_unlanded", "departs_landed", "answered", "mistake", "hand_off", "refusal",
            "lane", "pick_known_writer", "rewrite_stamp", "triage_hold", "unvetted_unreadable",
            "unvetted_cited", "rewrite_model", "rewrite_unstarted", "rewrite_answered", "rewrite_recovered")
FACT_SENTENCES = ("Pick guard: the page writer is session session_writer1 (decision guard-remedy-not-to-owner).",
                  "Names of the checks sit in the record. Keys are one option set per question.",
                  "The check reads the transcript, and a Done line holds one kind.")
ORDER_SENTENCES = ("Send it now: the report.", "Two questions; send the questions again.",
                   "Give the line. Keep it short.", "Do not write it again.", "Post only the corrected line.")


def setUpModule():
    trg.setUpModule()  # the config isolation, the model stub and the run folder, as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()
    shutil.rmtree(tcj.ROOT, ignore_errors=True)  # the repo fixtures' run folder, which trg does not remove


def session_problem(reason):
    """The session phrase, or the sentence that orders the session, that `reason` holds. '' when it holds neither."""
    low = reason.lower()
    for phrase in SESSION_PHRASES:
        if phrase in low:
            return phrase
    for unit in UNIT_END.split(reason):
        words = WORD.findall(unit.lower())
        if words and words[0] in IMPERATIVES:
            return unit.strip()
    return ""


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
    """One block path: the transcript `records`, the word the first sentence must hold, the repo `cwd`, the env and the
    hook fields (`extra`) the Stop needs, and `prep`, a case run first. A rewrite path blocks only after a
    missing-report block has left its marker, so its prep is that block."""
    return {"records": records, "word": word, "cwd": cwd, "env": env or {}, "extra": extra or {}, "prep": prep}


class RemedyReasons(trg.SameTurnWriter, unittest.TestCase):
    PAGE = tcj.PAGE_URL  # the waiting page tcj.make_repo names; the same-turn writer read cites it
    LANE_ID = trg.QuestionReachesPageTests.LANE_ID  # read by lane_record below, which takes self
    ARCHIVE = "mcp__claude-code-remote__archive_session"
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

    def refusal_repo_config(self):
        """A config folder whose refusals file holds one refused tool that the reply does not raise."""
        cfg = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        path = os.path.join(cfg, "state", "refusals", self.REFUSAL_SID + ".jsonl")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": "2026-11-01T10:00:00-05:00", "tool_name": self.ARCHIVE,
                                     "reason": "refused"}) + "\n")
        return cfg

    def rewrite(self, name, first, again, word, clean):
        """A missing-report block on `first`, then the rewrite `again` under the same session id, which the marker
        of that block reads. `first` and `again` hold the same turn up to the reply."""
        sid = "remedy-rewrite-" + name
        block = case(first, "report", clean, extra={"session_id": sid})
        return case(again, word, clean, extra={"session_id": sid, "stop_hook_active": True}, prep=block)

    def fixture(self, name):
        """The block path `name`, as a case dict. Every case names a cwd that tcj.make_repo built, so no check reads
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
            "keys": lambda: case([trg.human("decide"), *self.sent_to_writer(), trg.assistant_text(trg.KEYS_SAME)],
                                 "key", bare),
            "pick": lambda: case([trg.human("decide"), trg.assistant_text(trg.RELAY)], "pick", bare),
            # Recovered: a landed report after a compaction that carries no Recovered line.
            "recovered": lambda: case(trg.CompactionCarryTests.compacted_turn(trg.REPORT_NO_LINE), "recovered", clean),
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
            # Rewrite paths: the rewrite of a missing-report block is checked for the model, Unstarted, answered and
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

    def block_for(self, name):
        """(reason, word) of the block path `name`. The path must block, and its prep, when it has one, runs first."""
        c = self.fixture(name)
        if c["prep"]:
            first = self.run_stop(c["prep"])
            self.assertEqual(first.get("decision"), "block",
                             "%s: the block before the rewrite is missing: %r" % (name, first))
        out = self.run_stop(c)
        self.assertEqual(out.get("decision"), "block", "%s: the path does not block: %r" % (name, out))
        return out["reason"], c["word"]

    def check_no_session_problem(self, name, reason):
        problem = session_problem(reason)
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
        self.assertNotEqual(out.get("decision"), "block", "2 a clean report is blocked: %r" % out)

    def test_1a_control_fact_sentences_are_not_flagged(self):
        for fact in FACT_SENTENCES:
            self.assertEqual(session_problem(fact), "", "control: a fact sentence is flagged: %r" % fact)

    def test_1a_control_orders_are_flagged(self):
        for order in ORDER_SENTENCES:
            self.assertNotEqual(session_problem(order), "", "control: an order is not flagged: %r" % order)

    def test_3_record_has_a_step_heading_for_each_owner_line_check(self):
        # The names come from report_guard.py's own source, the one place each owner_line call is written.
        names = owner_line_checks()
        self.assertTrue(names, "report_guard passes no check name to owner_line")
        self.assertNotIn(None, names, "a check name is neither a literal nor a module constant: it cannot be read")
        self.assertTrue(os.path.exists(RECORD), "the decision record is missing: %s" % RECORD)
        with open(RECORD, encoding="utf-8") as handle:
            record = handle.read()
        for name in sorted(set(names)):
            base = name.split(" (")[0].strip()
            self.assertRegex(record, r"(?m)^### " + re.escape(base) + r"\b",
                             "the record holds no step heading for the check %r" % base)


def _case_1a(name):
    def test(self):
        reason, _ = self.block_for(name)
        self.check_no_session_problem(name, reason)
    return test


def _case_1b(name):
    def test(self):
        reason, _ = self.block_for(name)
        self.check_cites_record(name, reason)
    return test


def _case_1c(name):
    def test(self):
        reason, word = self.block_for(name)
        self.check_first_sentence(name, reason, word)
    return test


def _case_2(name):
    def test(self):
        self.block_for(name)  # asserts the block itself
    return test


for _name in FIXTURES:
    setattr(RemedyReasons, "test_1a_%s_no_session_phrase" % _name, _case_1a(_name))
    setattr(RemedyReasons, "test_1b_%s_cites_record" % _name, _case_1b(_name))
    setattr(RemedyReasons, "test_1c_%s_first_sentence_names_check" % _name, _case_1c(_name))
    setattr(RemedyReasons, "test_2_%s_still_blocks" % _name, _case_2(_name))


if __name__ == "__main__":
    unittest.main()
