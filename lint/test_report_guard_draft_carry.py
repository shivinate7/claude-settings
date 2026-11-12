#!/usr/bin/env python3
"""The Recovered guard drafts the carry line it refuses for, so a session pastes it instead of retyping it.

After a compaction, report_guard.py refuses a report that lacks a `Recovered:` or `Handoff gave:` line (decision
precompact-handoff, item 13). A refusal for a missing line also carries a ready-to-paste draft of that line, built from
the transcript the guard has already read. These cases pin what the draft holds:

- a Recovered draft names only the sources the transcript after the compaction shows: git, page, digest;
- a source counts only when its call's result came back without is_error, paired by tool_use_id;
- a call with no result at all is no source either: the transcript shows no read that came back;
- with no source read after the compaction, the Recovered draft is `Recovered: none`;
- a draft pasted back into the report unchanged passes the guard;
- a missing Handoff gave line drafts a placeholder, never `Handoff gave: none`, since the hook cannot know the facts;
- a report with no compaction, or with an unsourced item, drafts nothing;
- drafting starts no process and opens no file;
- the Stop block the owner sees carries the draft;
- a draft line in the Stop block ends before the next refusal reason, so a pasted line carries none of it;
- the Stop block prints the drafts last, each on its own line after the other reasons, on an unlanded turn and on the
  rewrite after a missing-report block.

The fixture, the record builders and the run folder come from lint/test_report_guard.py, the one home, borrowed by name
here. No model call is made. Run with:

    python3 lint/test_report_guard_draft_carry.py -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the fixture, record builders and run folder (one home)
import report_guard as RG  # noqa: E402  the refusal the check prints, and the owner-line citation (one home)

REPORT_GUARD = trg.REPORT_GUARD
REPORT = trg.REPORT_NO_LINE  # carries neither carry line
SOURCES = ("git", "page", "digest")
# The owner-line tail every refusal ends with. A draft is read up to it, so the tail is never part of the draft.
OWNER_TAIL = re.compile(r"\s*\(%s\)" % re.escape(RG.REMEDY_CITE))
# An answered-source refusal's trigger: a reply line that says "answered" and cites no source.
ANSWERED_LINE = "Answered: no permission rule can lift it."
# The rule suffix a joined Stop reason ends with, and the header it prints before the draft lines. The header is written
# out here, not read from report_guard, so the pin states the text the owner reads.
RULE_SUFFIX = " (rule reports-order-of-labels)"
DRAFT_HEADER = "\nDraft of each missing line:\n"


def setUpModule():
    trg.setUpModule()  # the run folder and CLAUDE_CONFIG_DIR, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


def call(name, input_, ok=True, answered=True):
    """One tool call and its result, paired by tool_use_id as a transcript pairs them. `ok` False makes the result
    an error (is_error true): a call that failed. `answered` False drops the result: the call has none at all."""
    use_id = "toolu_" + uuid.uuid4().hex
    uses = [trg.tool_use_msg(name, input_, id_=use_id)]
    return (uses + [trg.tool_result_msg(tool_use_id=use_id, is_error=not ok)]) if answered else uses


def git_read(ok=True, answered=True):
    return call("Bash", {"command": "git log --oneline -1"}, ok, answered)


def code_read():
    """A read of a repo file. It names no source, so the draft leaves it out."""
    return call("Read", {"file_path": "/fixture/repo/lint/report_guard.py"})


def digest_read(ok=True, answered=True):
    return call("Read", {"file_path": "/fixture/config/handoffs/cc-fixture.md"}, ok, answered)


def page_read(ok=True, answered=True):
    return call("Artifact", {"action": "read", "url": "https://claude.ai/artifact/fixture-page"}, ok, answered)


def compacted(*middle):
    """A transcript with a compaction, then the `middle` records after it."""
    return [trg.human("do the task"), trg.compact_boundary(), trg.compact_summary(), *middle]


def compacts(records):
    return any(rec.get("subtype") == "compact_boundary" for rec in records)


def _content(rec):
    content = (rec.get("message") or {}).get("content")
    return content if isinstance(content, list) else []


def errored(records):
    """The results in `records` that set is_error true and answer a call the records make, paired by tool_use_id."""
    blocks = [b for rec in records for b in _content(rec) if isinstance(b, dict)]
    called = {b.get("id") for b in blocks if b.get("type") == "tool_use"}
    return [b for b in blocks if b.get("type") == "tool_result" and b.get("is_error") is True
            and b.get("tool_use_id") in called]


def calls_in(records):
    """The tool_use blocks in `records`."""
    return [b for rec in records for b in _content(rec) if isinstance(b, dict) and b.get("type") == "tool_use"]


def results_in(records):
    """The tool_result blocks in `records`, errored or not."""
    return [b for rec in records for b in _content(rec) if isinstance(b, dict) and b.get("type") == "tool_result"]


def cited(report):
    """The report with a bare record id, D12, in its Next line. The Cite-gloss guard refuses it: no gloss beside it."""
    return report.replace("ship it", "ship it per D12")


def landed():
    """A git commit: the turn lands, and the Stop check reads the reply's reasons on a landed turn only."""
    return call("Bash", {"command": "git commit -m x"})


def drafted(refusal, label):
    """The draft line that starts at `label` in a refusal, read to the end of its line without the owner tail. None
    when the refusal holds no such label."""
    found = re.search(r"\b%s" % re.escape(label), refusal or "")
    if not found:
        return None
    line = refusal[found.start():].split("\n", 1)[0]
    return OWNER_TAIL.split(line, 1)[0].strip(" .")


def draft_sources(draft):
    """The source words the draft names, in SOURCES order."""
    return [word for word in SOURCES if re.search(r"\b%s\b" % word, draft)]


def assert_drafts_last(case, reason, others, labels):
    """The Stop reason prints the other reasons before the draft header, the rule suffix right before the header, then
    each draft on its own line. `others` are texts the reasons before the header hold; `labels` name the draft lines in
    order. Returns the draft lines."""
    head, sep, tail = reason.partition(DRAFT_HEADER)
    case.assertTrue(sep, "the Stop reason holds no draft header: %r" % reason)
    for text in others:
        case.assertIn(text, head, "the reason %r is not printed before the draft header: %r" % (text, reason))
    case.assertTrue(head.endswith(RULE_SUFFIX), "the rule suffix is not right before the draft header: %r" % reason)
    lines = tail.split("\n")
    case.assertEqual([ln.partition(":")[0] for ln in lines], labels,
                     "the lines after the draft header are not the draft lines %r: %r" % (labels, reason))
    for ln in lines:
        case.assertNotIn(RULE_SUFFIX, ln, "the rule suffix sits on a draft line: %r" % ln)
    return lines


class RecoveredDraftTests(unittest.TestCase):
    """The draft the Recovered guard prints for a missing carry line, read from the transcript after the compaction."""

    def test_recovered_draft_names_only_the_sources_the_transcript_shows(self):
        records = compacted(*git_read(), *code_read())
        self.assertTrue(compacts(records), "the transcript holds no compaction, so the drafting path is not what runs")
        refusal = RG.recovered_problem(records, REPORT)
        self.assertTrue(refusal, "no refusal for a report after a compaction with no carry lines")
        draft = drafted(refusal, "Recovered:")
        self.assertIsNotNone(draft, "the refusal carries no Recovered draft: %r" % refusal)
        # Catches: a source named that the transcript never read, or a source left out that it did read.
        self.assertEqual(draft_sources(draft), ["git"],
                         "the Recovered draft %r names %r; the transcript read git alone"
                         % (draft, draft_sources(draft)))
        self.assertIsNotNone(drafted(refusal, "Handoff gave:"), "the refusal drafts no Handoff gave line: %r" % refusal)
        self.assertEqual(RG.session_wording(refusal), "",
                         "the refusal reads as an order to the session, not as facts: %r" % refusal)

    def test_no_source_read_after_the_compaction_drafts_recovered_none(self):
        cases = {
            "nothing read after the compaction": compacted(),
            # Catches: a git read from before the compaction counts toward the draft.
            "a git read before the compaction": [trg.human("do the task"), *git_read(),
                                                 trg.compact_boundary(), trg.compact_summary()],
        }
        for label, records in cases.items():
            with self.subTest(case=label):
                self.assertTrue(compacts(records), "the transcript holds no compaction for %s" % label)
                draft = drafted(RG.recovered_problem(records, REPORT), "Recovered:")
                self.assertEqual(draft, "Recovered: none",
                                 "the Recovered draft for %s is %r, not Recovered: none" % (label, draft))

    def test_a_draft_pasted_back_unchanged_passes_the_guard(self):
        cases = {
            "a git read": compacted(*git_read()),
            "nothing read": compacted(),
            "every source read": compacted(*git_read(), *digest_read(), *page_read()),
        }
        for label, records in cases.items():
            with self.subTest(case=label):
                self.assertTrue(compacts(records), "the transcript holds no compaction for %s" % label)
                refusal = RG.recovered_problem(records, trg.report_lines("Handoff gave: none"))
                self.assertTrue(refusal, "no refusal for a report with no Recovered line, %s" % label)
                draft = drafted(refusal, "Recovered:")
                self.assertIsNotNone(draft, "the refusal carries no Recovered draft to paste: %r" % refusal)
                again = RG.recovered_problem(records, trg.report_lines("Handoff gave: none", draft))
                self.assertEqual(again, "", "the draft %r, pasted unchanged, still refuses: %r" % (draft, again))

    def test_a_transcript_that_shows_every_source_drafts_every_source_word(self):
        # Full size: a long run of reads between the compaction and the report, with each source read among them.
        middle = []
        for _ in range(100):
            middle += code_read()
        middle += git_read() + page_read() + digest_read()
        records = compacted(*middle)
        self.assertTrue(compacts(records), "the transcript holds no compaction, so the drafting path is not what runs")
        refusal = RG.recovered_problem(records, REPORT)
        draft = drafted(refusal, "Recovered:")
        self.assertIsNotNone(draft, "the refusal carries no Recovered draft: %r" % refusal)
        self.assertEqual(draft_sources(draft), ["git", "page", "digest"],
                         "the Recovered draft %r leaves out a source the transcript read" % draft)

    def test_a_missing_handoff_gave_line_drafts_a_placeholder_never_none(self):
        records = compacted(*git_read())
        self.assertTrue(compacts(records), "the transcript holds no compaction, so the drafting path is not what runs")
        report = trg.report_lines("Recovered: ruling X from PR 978 (git)")
        refusal = RG.recovered_problem(records, report)
        self.assertTrue(refusal, "no refusal for a report with no Handoff gave line")
        # Catches: "none" drafted for a line the hook cannot know, since the handoff may hold facts the summary lacks.
        self.assertNotIn("Handoff gave: none", refusal, "the refusal drafts Handoff gave: none: %r" % refusal)
        draft = drafted(refusal, "Handoff gave:")
        self.assertIsNotNone(draft, "the refusal carries no Handoff gave draft: %r" % refusal)
        # Catches: a Recovered draft for a report whose Recovered line already landed.
        self.assertIsNone(drafted(refusal, "Recovered:"), "the refusal drafts a Recovered line that landed: %r" % refusal)
        again = RG.recovered_problem(records, trg.report_lines("Recovered: ruling X from PR 978 (git)", draft))
        self.assertEqual(again, "", "the Handoff gave draft %r, pasted unchanged, still refuses: %r" % (draft, again))


class ErroredSourceTests(unittest.TestCase):
    """A call whose result is an error is no source: the transcript did not show the read it asked for."""

    def test_an_errored_source_call_drafts_no_source(self):
        cases = {
            "a digest Read that errored": digest_read(ok=False),
            "a git status that errored": call("Bash", {"command": "git status"}, ok=False),
            "an Artifact read that errored": page_read(ok=False),
            # Full size: a long run of failed reads of the handoff file, none of them read.
            "100 digest Reads that errored": [r for _ in range(100) for r in digest_read(ok=False)],
        }
        for label, middle in cases.items():
            with self.subTest(case=label):
                records = compacted(*middle)
                self.assertTrue(compacts(records), "the transcript holds no compaction for %s" % label)
                self.assertTrue(errored(records), "the transcript holds no errored result for %s, so the failed path "
                                "is not what runs" % label)
                draft = drafted(RG.recovered_problem(records, REPORT), "Recovered:")
                self.assertEqual(draft, "Recovered: none",
                                 "the Recovered draft for %s is %r, not Recovered: none, though its result errored"
                                 % (label, draft))

    def test_a_failed_call_beside_a_good_one_drafts_only_the_good_source(self):
        records = compacted(*call("Bash", {"command": "git status"}, ok=False), *page_read())
        self.assertTrue(errored(records), "the transcript holds no errored git result, so the mixed path is not what runs")
        draft = drafted(RG.recovered_problem(records, REPORT), "Recovered:")
        # Catches: one failed call dropping every source, or a failed call counting as its source.
        self.assertEqual(draft_sources(draft), ["page"],
                         "the Recovered draft %r names %r; the git call errored and the page read did not"
                         % (draft, draft_sources(draft)))


class UnansweredSourceTests(unittest.TestCase):
    """A call with no result at all is no source either: the transcript shows no read that came back."""

    def test_a_call_with_no_result_drafts_no_source(self):
        all_three = [*git_read(answered=False), *digest_read(answered=False), *page_read(answered=False)]
        cases = {
            "a git call with no result": git_read(answered=False),
            "a handoffs Read with no result": digest_read(answered=False),
            "an Artifact read with no result": page_read(answered=False),
            "all three with no result": all_three,
            # Full size: a long run of handoff reads, none of them with a result.
            "100 digest Reads with no result": [r for _ in range(100) for r in digest_read(answered=False)],
        }
        for label, middle in cases.items():
            with self.subTest(case=label):
                records = compacted(*middle)
                self.assertTrue(compacts(records), "the transcript holds no compaction for %s" % label)
                # Scope first: the calls are in the transcript, and no result answers any of them.
                self.assertTrue(calls_in(records), "the transcript holds no call for %s" % label)
                self.assertEqual(results_in(records), [], "the transcript holds a result for %s, so the no-result path "
                                 "is not what runs" % label)
                draft = drafted(RG.recovered_problem(records, REPORT), "Recovered:")
                # Catches: a call with no result counted as a source the session read.
                self.assertEqual(draft, "Recovered: none",
                                 "the Recovered draft for %s is %r, not Recovered: none, though no result came back"
                                 % (label, draft))

    def test_the_same_calls_with_their_results_draft_their_sources(self):
        # Control, green on the code before the change: with their results, the same calls draft their sources, so the
        # no-result case above fails for the missing result and for nothing else.
        records = compacted(*git_read(), *digest_read(), *page_read())
        draft = drafted(RG.recovered_problem(records, REPORT), "Recovered:")
        self.assertEqual(draft_sources(draft), ["git", "page", "digest"],
                         "the Recovered draft %r does not name the three sources the transcript read" % draft)


class DraftControlTests(unittest.TestCase):
    """Cases the draft must leave alone. They pass on the code before the draft, so they hold it to today's refusals."""

    def test_a_successful_call_drafts_its_source(self):
        # Control, green on the code before the change: a call whose result is fine still drafts its source. A failed
        # read followed by a good retry of the same file drafts that file, so the failed call is not what counts.
        cases = {
            "a git read": (git_read(), ["git"]),
            "a digest read": (digest_read(), ["digest"]),
            "a page read": (page_read(), ["page"]),
            "a failed digest read, then a good retry": (digest_read(ok=False) + digest_read(), ["digest"]),
        }
        for label, (middle, want) in cases.items():
            with self.subTest(case=label):
                records = compacted(*middle)
                self.assertTrue(compacts(records), "the transcript holds no compaction for %s" % label)
                draft = drafted(RG.recovered_problem(records, REPORT), "Recovered:")
                self.assertEqual(draft_sources(draft), want,
                                 "the Recovered draft for %s is %r and names %r, not %r"
                                 % (label, draft, draft_sources(draft), want))

    def test_no_compaction_drafts_nothing(self):
        records = [trg.human("do the task"), *git_read()]
        self.assertFalse(compacts(records), "the transcript holds a compaction, so this is not the no-compaction path")
        refusal = RG.recovered_problem(records, REPORT)
        self.assertEqual(refusal, "", "a report with no compaction is refused: %r" % refusal)

    def test_an_unsourced_recovered_item_drafts_nothing(self):
        # The draft covers a missing line only. An item that names no source is refused as before, with no draft.
        records = compacted(*git_read())
        self.assertTrue(compacts(records), "the transcript holds no compaction, so the unsourced path is not what runs")
        refusal = RG.recovered_problem(records, trg.report_lines("Recovered: ruling X", "Handoff gave: none"))
        self.assertIn("names no source", refusal, "the refusal is not the unsourced-item refusal: %r" % refusal)
        self.assertIsNone(drafted(refusal, "Recovered:"), "the unsourced refusal drafts a line: %r" % refusal)


class DraftCostTests(unittest.TestCase):
    """Drafting reads the records the guard already read. It starts no process and opens no file (decision
    precompact-handoff, item 13: no new log, file or process)."""

    def test_drafting_starts_no_process_and_opens_no_file(self):
        records = compacted(*git_read())
        # Control: the patch sees a start, so the zero counts below mean the draft started none.
        with mock.patch("subprocess.Popen") as control:
            subprocess.Popen(["true"])
        self.assertEqual(control.call_count, 1, "the patch did not see a start, so the zero counts prove nothing")
        with mock.patch("subprocess.Popen") as popen, mock.patch("os.system") as system, \
                mock.patch("builtins.open", wraps=open) as opened:
            refusal = RG.recovered_problem(records, REPORT)
        self.assertIsNotNone(drafted(refusal, "Recovered:"), "no draft to measure the cost of: %r" % refusal)
        self.assertEqual(popen.call_count, 0, "drafting started %d processes" % popen.call_count)
        self.assertEqual(system.call_count, 0, "drafting ran os.system %d times" % system.call_count)
        self.assertEqual(opened.call_count, 0, "drafting opened %d files; the transcript is already read"
                         % opened.call_count)


class DraftStopTests(unittest.TestCase):
    """The block the Stop hook prints carries the draft, so the owner's refusal and the session's paste match."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)

    def stop_block(self, records):
        """The Stop hook's output for `records` as a transcript: the block the owner sees, or None when it prints none."""
        path = trg.write_transcript(records, self.folder)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False,
                "session_id": "cc-" + uuid.uuid4().hex}
        run = trg.run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet"))
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def test_the_stop_block_carries_the_drafted_line(self):
        records = compacted(*git_read(), trg.assistant_text(REPORT))
        direct = RG.recovered_problem(records, REPORT)
        draft = drafted(direct, "Recovered:")
        self.assertIsNotNone(draft, "the refusal carries no Recovered draft: %r" % direct)
        out = self.stop_block(records)
        self.assertIsNotNone(out, "the Stop printed no block for a report with no carry lines")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(draft, out["reason"], "the Stop block leaves out the draft %r: %r" % (draft, out["reason"]))

    def test_a_draft_line_ends_before_the_next_reason_in_the_stop_block(self):
        # The Cite-gloss reason follows the drafts in the block. A draft line a session pastes carries none of it.
        cases = {
            "both carry lines missing": (cited(REPORT), ("Recovered:", "Handoff gave:")),
            "only the Recovered line missing": (cited(trg.report_lines("Handoff gave: none")), ("Recovered:",)),
        }
        for label, (report, labels) in cases.items():
            with self.subTest(case=label):
                # Scope first: the report is refused for its bare id, and the Stop block carries that refusal.
                self.assertTrue(RG.report_shape_ok(report), "the report is not in the Done-block shape: %r" % report)
                self.assertEqual(RG.bare_cite(report), "D12", "the report holds no bare id for the Cite-gloss reason")
                out = self.stop_block(compacted(*landed(), *git_read(), trg.assistant_text(report)))
                self.assertIsNotNone(out, "the Stop printed no block for %s" % label)
                self.assertEqual(out.get("decision"), "block")
                self.assertIn("Cite-gloss guard", out["reason"],
                              "the Stop block holds no Cite-gloss reason for %s: %r" % (label, out["reason"]))
                for name in labels:
                    line = next((ln for ln in out["reason"].split("\n") if name in ln), None)
                    self.assertIsNotNone(line, "the Stop block holds no %s line for %s: %r"
                                         % (name, label, out["reason"]))
                    self.assertNotIn("Cite-gloss", line, "the %s draft line for %s carries the next reason: %r"
                                     % (name, label, line))

    def test_an_unlanded_stop_prints_the_drafts_last_on_their_own_lines(self):
        # The pick join: a turn with no call (no commit, push or merge), holding an answered-source refusal and the
        # Recovered refusal with both draft lines.
        records = compacted(trg.assistant_text(ANSWERED_LINE + "\n\n" + REPORT))
        # Scope first: the turn holds no call, so it is the unlanded path.
        self.assertEqual(calls_in(records), [], "the turn holds a call, so it is not the unlanded path")
        out = self.stop_block(records)
        self.assertIsNotNone(out, "the Stop printed no block for an unlanded turn with two refusals")
        self.assertEqual(out.get("decision"), "block")
        lines = assert_drafts_last(self, out["reason"], ["Answered guard", "Recovered guard"],
                                   ["Recovered", "Handoff gave"])
        # Catches: a Recovered draft that names a source, though no source was read after the compaction.
        self.assertEqual(lines[0], "Recovered: none", "the Recovered draft is %r, not Recovered: none" % lines[0])


class DraftRewriteStopTests(unittest.TestCase):
    """The rewrite after a missing-report block prints the drafts last too: the rewrite join."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=trg.RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.sid = "cc-" + uuid.uuid4().hex

    def stop(self, records, active):
        path = trg.write_transcript(records, self.folder)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active,
                "session_id": self.sid}
        run = trg.run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet"))
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def test_the_rewrite_after_a_missing_report_prints_the_drafts_last(self):
        # The first Stop lands a commit with no report: it blocks for the report and leaves the marker the rewrite reads.
        first = self.stop(compacted(*landed(), trg.assistant_text("All done.")), False)
        self.assertIsNotNone(first, "no missing-report block on the first Stop")
        self.assertIn("does not end with the report", first["reason"], "the first Stop is not the missing-report block")
        out = self.stop(compacted(*landed(), trg.assistant_text(ANSWERED_LINE + "\n\n" + REPORT)), True)
        self.assertIsNotNone(out, "the rewrite printed no block for a reply with two refusals")
        self.assertEqual(out.get("decision"), "block")
        lines = assert_drafts_last(self, out["reason"], ["Answered guard", "Recovered guard"],
                                   ["Recovered", "Handoff gave"])
        # The commit after the compaction is a git source, so the Recovered draft names git and no other source.
        self.assertEqual(draft_sources(lines[0]), ["git"], "the Recovered draft is %r, not one naming git" % lines[0])


if __name__ == "__main__":
    unittest.main()
