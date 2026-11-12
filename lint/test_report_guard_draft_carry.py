#!/usr/bin/env python3
"""The Recovered guard drafts the carry line it refuses for, so a session pastes it instead of retyping it.

After a compaction, report_guard.py refuses a report that lacks a `Recovered:` or `Handoff gave:` line (decision
precompact-handoff, item 13). A refusal for a missing line also carries a ready-to-paste draft of that line, built from
the transcript the guard has already read. These cases pin what the draft holds:

- a Recovered draft names only the sources the transcript after the compaction shows: git, page, digest;
- with no source read after the compaction, the Recovered draft is `Recovered: none`;
- a draft pasted back into the report unchanged passes the guard;
- a missing Handoff gave line drafts a placeholder, never `Handoff gave: none`, since the hook cannot know the facts;
- a report with no compaction, or with an unsourced item, drafts nothing;
- drafting starts no process and opens no file;
- the Stop block the owner sees carries the draft.

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


def setUpModule():
    trg.setUpModule()  # the run folder and CLAUDE_CONFIG_DIR, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


def call(name, input_):
    """One tool call and its result, as the two transcript records they are."""
    return [trg.tool_use_msg(name, input_), trg.tool_result_msg()]


def git_read():
    return call("Bash", {"command": "git log --oneline -1"})


def code_read():
    """A read of a repo file. It names no source, so the draft leaves it out."""
    return call("Read", {"file_path": "/fixture/repo/lint/report_guard.py"})


def digest_read():
    return call("Read", {"file_path": "/fixture/config/handoffs/cc-fixture.md"})


def page_read():
    return call("Artifact", {"action": "read", "url": "https://claude.ai/artifact/fixture-page"})


def compacted(*middle):
    """A transcript with a compaction, then the `middle` records after it."""
    return [trg.human("do the task"), trg.compact_boundary(), trg.compact_summary(), *middle]


def compacts(records):
    return any(rec.get("subtype") == "compact_boundary" for rec in records)


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


class DraftControlTests(unittest.TestCase):
    """Cases the draft must leave alone. They pass on the code before the draft, so they hold it to today's refusals."""

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

    def test_the_stop_block_carries_the_drafted_line(self):
        records = compacted(*git_read(), trg.assistant_text(REPORT))
        direct = RG.recovered_problem(records, REPORT)
        draft = drafted(direct, "Recovered:")
        self.assertIsNotNone(draft, "the refusal carries no Recovered draft: %r" % direct)
        path = trg.write_transcript(records, self.folder)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False,
                "session_id": "cc-" + uuid.uuid4().hex}
        run = trg.run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet"))
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        out = json.loads(run.stdout) if run.stdout.strip() else None
        self.assertIsNotNone(out, "the Stop printed no block for a report with no carry lines")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(draft, out["reason"], "the Stop block leaves out the draft %r: %r" % (draft, out["reason"]))


if __name__ == "__main__":
    unittest.main()
