#!/usr/bin/env python3
"""Stop report guard: an Input Needed item that cites a closed waiting-page item.

The check reads only the Input Needed item (report_guard.input_needed_section). A cite is `item N`, `page item N`,
a list `items N, M and K` (joined by commas, "and", "&" or "or"), or `page:N`. `#N` is a PR number, so it is no cite.
Punctuation or bold around the word (`Items:`, `**item**`) is still a cite of the number after it.
The status of each cited number comes from the waiting copy on origin/<record branch>, one JSON file per item, read
by feedback_guard.waiting_statuses. A line that cites a closed item blocks, and the reason names only the closed
numbers. These pass: a ruling cite (a ref, then an option letter, "pick <letter>", or "note" that ends its clause,
alone or with combined letters such as `a+c`); a line that starts with the question-form label `Based on (` or
`Departs from:`; a closed ref, where "closed" follows the ref directly; and a closed item cited outside Input Needed.
A copy that cannot be read, or an error inside the check, is unknown: no block, and a systemMessage that says UNKNOWN.
A report that cites no item reads no status, so it makes no git call.

    python3 lint/test_report_guard_page_status.py -v
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "hooks")
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the transcript helpers, the guard path and the run isolation (one home)
sys.path.insert(0, HOOKS)
import test_feedback_inbox as tfi  # noqa: E402  the waiting-page repo builders and the git helpers (one home)
import feedback_guard  # noqa: E402  waiting_statuses, the one reader of the waiting copy (the cost cases patch it)
import report_guard  # noqa: E402  main, the Stop guard run in this process

RUN_FOLDER = trg.RUN_FOLDER  # this run's one folder (test-temp-standard); every case takes its folder from it
# test_feedback_inbox made its own run folder when it was imported. Its builders take their folder from ROOT at call
# time, so they build under this run's folder instead, and the import's empty folder goes.
_IMPORTED_ROOT = tfi.ROOT
tfi.ROOT = RUN_FOLDER
shutil.rmtree(_IMPORTED_ROOT, ignore_errors=True)

PAGE_URL = tfi.PAGE_URL  # the waiting page URL of the feedback fixtures
RECORD_BRANCH = tfi.RECORD_BRANCH  # roadmap, the branch a repo reads with no record-branch key
# The copy the cases read: (item id, n, status). 214, 381, 383 and 222 are the incident's list, all closed. 109, 127
# and 131 are closed too, so a ruling cite on each is a real control. 365 is open.
COPY = (
    ("item-109", 109, "closed"),
    ("item-127", 127, "closed"),
    ("item-131", 131, "closed"),
    ("item-214", 214, "closed"),
    ("item-222", 222, "closed"),
    ("item-365", 365, "open"),
    ("item-381", 381, "closed"),
    ("item-383", 383, "closed"),
)
# The full-size copy: 39 open items, then one closed item.
FULL = tuple(("filler-%02d" % i, 300 + i, "open") for i in range(39)) + (("item-139", 139, "closed"),)
# A question with no send to the page writer. In a waiting-page repo the question check blocks it, so it proves the
# fixture reaches the Input Needed reads before an empty output is read as a pass.
WITNESS_QUESTION = "Which way should the copy go?"


def setUpModule():
    trg.setUpModule()


def tearDownModule():
    trg.tearDownModule()  # removes RUN_FOLDER, which holds every fixture repo of this module


def status_files(items):
    """{path: text} for a waiting copy whose items carry a status. tfi.copy_files writes each item file (its path and
    its numeric n); this adds the status field to each one."""
    status = {n: state for _, n, state in items}
    files = {}
    for rel, text in tfi.copy_files(tuple((item_id, n) for item_id, n, _ in items)).items():
        data = json.loads(text)
        data["status"] = status[data["n"]]
        files[rel] = json.dumps(data)
    return files


def status_repo(key, items, branch=RECORD_BRANCH, extras=None):
    """A waiting-page repo whose record branch holds the status copy on origin/<branch> only (tfi.record_repo)."""
    return tfi.record_repo(key, status_files(items), branch=branch, extras=extras)


def copy_repo():
    return status_repo("ps-copy", COPY)


def full_repo():
    return status_repo("ps-full", FULL)


def named_repo():
    """The copy is on the record branch the extras name, and the default roadmap holds none."""
    return status_repo("ps-named", COPY, branch="records", extras=tfi.filing_extras("records"))


def no_folder_repo():
    return tfi.record_repo("ps-no-folder", {"README.txt": "no copy\n"})


def torn_repo():
    """The record branch ref points at no object, so git cannot read it."""
    return tfi.record_repo("ps-torn", status_files(COPY), torn=True)


def corrupt_repo():
    """The one item file is cut short: not JSON."""
    return tfi.record_repo("ps-corrupt", {"waiting/items/item-214.json": tfi.CORRUPT_ITEM})


def local_copy_repo():
    """A waiting-page repo whose copy is on the local record branch only. No origin ref holds it."""
    def build():
        root = tfi.make_repo("ps-local-only", tracked=("decisions/a-ruling.md",), extras=tfi.filing_extras())
        tfi.git(root, "checkout", "-q", "-b", RECORD_BRANCH)
        for rel, text in status_files(COPY).items():
            tfi.write_file(os.path.join(root, *rel.split("/")), text)
        tfi.git(root, "add", "-A")
        tfi.git(root, "commit", "-q", "-m", "record branch")
        tfi.git(root, "checkout", "-q", "main")
        return root
    return tfi.shared_repo("ps-local-only", build)


def no_branch_repo():
    """A waiting-page repo with no record branch at all, so there is no copy to read."""
    return tfi.shared_repo("ps-no-branch", lambda: tfi.make_repo(
        "ps-no-branch", tracked=("decisions/a-ruling.md",), extras=tfi.filing_extras()))


def no_page_repo():
    """A repo that names no waiting page: no extras file, so layout.waiting_page reads "unknown"."""
    return tfi.shared_repo("ps-no-page", lambda: tfi.make_repo("ps-no-page", tracked=("decisions/a-ruling.md",)))


def report(input_lines, done="OTHER: waiting copy checked", deviations="none", nxt="ship it"):
    """A report block: Done, Deviations, Input Needed (one blockquote line per entry of `input_lines`), and Next."""
    lines = ["> **Done** " + done, "> **Deviations** " + deviations, "> **Input Needed** " + input_lines[0]]
    lines += ["> " + line for line in input_lines[1:]]
    lines.append("> **Next** " + nxt)
    return "\n".join(lines)


def number_re(n):
    return r"(?<!\d)%d(?!\d)" % n


class PageStatusTests(unittest.TestCase):
    def transcript(self, reply, landed):
        """A transcript path: one human message, a git commit call when `landed`, then the reply."""
        records = [trg.human("do the task")]
        if landed:
            records += [trg.tool_use_msg("Bash", {"command": "git commit -m x"}), trg.tool_result_msg()]
        records.append(trg.assistant_text(reply))
        return trg.write_transcript(records, tempfile.mkdtemp(dir=RUN_FOLDER))

    def run_turn(self, reply, landed, cwd):
        """The Stop guard as a subprocess on one turn, in the session folder `cwd`. Returns the finished process."""
        hook = {"hook_event_name": "Stop", "transcript_path": self.transcript(reply, landed),
                "stop_hook_active": False, "cwd": cwd}
        return trg.run_guard(trg.REPORT_GUARD, hook)

    def output_of(self, run, label):
        self.assertEqual(run.returncode, 0, "the guard crashed on %s: %s" % (label, run.stderr[-300:]))
        return json.loads(run.stdout) if run.stdout.strip() else {}

    def assert_scope(self, cwd, landed):
        """Scope before subject: the witness question must block in this fixture, so the guard reads the reply."""
        obj = self.output_of(self.run_turn(report([WITNESS_QUESTION]), landed, cwd), "the witness")
        self.assertEqual(obj.get("decision"), "block",
                         "scope: the witness question did not block, so the fixture does not reach the guard "
                         "(landed=%s)" % landed)

    def assert_blocks(self, cwd, text, numbers, absent=(), landed=True):
        """The reply cites the closed `numbers` in Input Needed: it blocks, and its reason names each closed number
        and no number in `absent`."""
        self.assert_scope(cwd, landed)
        label = "%r, landed=%s" % (text[:160], landed)
        obj = self.output_of(self.run_turn(text, landed, cwd), label)
        self.assertEqual(obj.get("decision"), "block", "a closed item cited in Input Needed did not block: %s" % label)
        reason = obj.get("reason") or ""
        for n in numbers:
            self.assertRegex(reason, number_re(n), "the block does not name closed item %d: %s" % (n, label))
        for n in absent:
            self.assertNotRegex(reason, number_re(n), "the block names open item %d: %s" % (n, label))

    def assert_quiet(self, cwd, text, landed=True):
        """The reply passes the check: no block and no output at all."""
        self.assert_scope(cwd, landed)
        run = self.run_turn(text, landed, cwd)
        self.assertEqual(run.returncode, 0, "the guard crashed on a passing reply: %s" % run.stderr[-300:])
        self.assertEqual(run.stdout.strip(), "",
                         "a reply that passes the status check got guard output: %r" % run.stdout[:300])

    def assert_unknown(self, cwd, text, landed=True):
        """The copy cannot be read: no block, and a systemMessage that says UNKNOWN."""
        self.assert_scope(cwd, landed)
        obj = self.output_of(self.run_turn(text, landed, cwd), "an unreadable copy, landed=%s" % landed)
        self.assertNotEqual(obj.get("decision"), "block", "an unreadable copy blocked a cited item: landed=%s" % landed)
        self.assertIn("UNKNOWN", obj.get("systemMessage") or "",
                      "an unreadable copy gave no UNKNOWN systemMessage: landed=%s" % landed)

    def run_in_process(self, cwd, text, landed, statuses=None, error=None):
        """report_guard.main() in this process, as the Stop hook runs it. The waiting-copy reader is patched to return
        `statuses`, or to raise `error` when one is given. Returns (the reader mock, the printed output, the exception
        main() let out or None). An exception is returned, not raised, so the case fails on its own assert."""
        hook = {"hook_event_name": "Stop", "transcript_path": self.transcript(text, landed),
                "stop_hook_active": False, "cwd": cwd}
        out = io.StringIO()
        raised = None
        mode = {"side_effect": error} if error is not None else {"return_value": statuses}
        with mock.patch.object(feedback_guard, "waiting_statuses", create=True, **mode) as reader, \
                mock.patch("sys.stdin", io.StringIO(json.dumps(hook))), contextlib.redirect_stdout(out):
            try:
                report_guard.main()
            except Exception as err:
                raised = err
        return reader, out.getvalue(), raised

    # --- blocks: a closed item cited in Input Needed ---

    def test_ps_red_a_closed_item_cite_in_input_needed_blocks(self):
        # Catches: an Input Needed item that cites a closed waiting-page item passes, so the owner is asked about
        # work the page has already closed. Each form of the cite, on a landed and an unlanded turn.
        for landed in (True, False):
            for line in ("Waiting on you: item 214.", "Waiting on you: page item 214.", "Waiting on you: page:214."):
                with self.subTest(line=line, landed=landed):
                    self.assert_blocks(copy_repo(), report([line]), (214,), landed=landed)

    def test_ps_red_the_coordinators_list_blocks_naming_each_closed_item(self):
        # Catches: the incident's list, "items 214, 381, 383 and 222", passes though all four are closed on the page.
        for landed in (True, False):
            with self.subTest(landed=landed):
                self.assert_blocks(copy_repo(), report(["Waiting on you: items 214, 381, 383 and 222."]),
                                   (214, 381, 383, 222), landed=landed)

    def test_ps_red_each_list_joiner_blocks(self):
        # Catches: a list joined by "&", by "or", or by a comma and "and" hides its closed numbers from the check.
        cases = (("items 214 & 381.", (214, 381)), ("items 214 or 381.", (214, 381)),
                 ("items 214, 381, and 383.", (214, 381, 383)))
        for line, numbers in cases:
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_blocks(copy_repo(), report(["Waiting on you: " + line]), numbers, landed=landed)

    def test_ps_red_a_mixed_list_names_only_its_closed_numbers(self):
        # Catches: a list with one open item blocks, but names every number in it, the open one included.
        self.assert_blocks(copy_repo(), report(["Waiting on you: items 365, 214 and 381."]), (214, 381),
                           absent=(365,))

    def test_ps_red_a_cite_on_a_later_line_of_input_needed_blocks(self):
        # Catches: the check reads only the first line of Input Needed, so a closed cite on a later line passes.
        self.assert_blocks(copy_repo(), report(["None new.", "- Waiting on you: item 214."]), (214,))

    def test_ps_red_a_closed_item_in_a_full_size_copy_blocks(self):
        # Catches: the check stops reading a copy of many files, so a closed item at the end of it passes.
        self.assert_blocks(full_repo(), report(["Waiting on you: item 139."]), (139,))

    def test_ps_red_the_record_branch_the_layout_names_is_read(self):
        # Catches: the check reads roadmap, not the record branch the layout names, so a copy on that branch passes.
        self.assert_blocks(named_repo(), report(["Waiting on you: item 214."]), (214,))

    def test_ps_red_a_based_on_line_without_the_question_form_blocks(self):
        # Catches: a line that starts "Based on" with no "(" is exempt, so a closed cite on it passes unasked.
        cases = (("Based on the page, items 214 and 381 wait on you", (214, 381)),
                 ("- **Based on** item 214 on the page, nothing waits.", (214,)))
        for line, numbers in cases:
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_blocks(copy_repo(), report(["None new.", line]), numbers, landed=landed)

    def test_ps_red_a_pick_that_is_not_a_letter_blocks(self):
        # Catches: "pick" exempts the ref before it whatever follows, so "pick one of A or B" passes a closed cite.
        # The question check also blocks this line in a waiting-page repo; the reason must still name 214 and 381.
        for landed in (True, False):
            with self.subTest(landed=landed):
                self.assert_blocks(copy_repo(), report(["None new.", "items 214 and 381: pick one of A or B"]),
                                   (214, 381), landed=landed)

    def test_ps_red_a_note_that_does_not_end_its_clause_blocks(self):
        # Catches: "note" exempts the ref before it wherever it stands, so "item 127 note on the page" passes.
        for landed in (True, False):
            with self.subTest(landed=landed):
                self.assert_blocks(copy_repo(), report(["None new.", "item 127 note on the page, still open"]), (127,),
                                   landed=landed)

    def test_ps_red_a_closed_word_exempts_only_the_ref_it_follows(self):
        # Catches: a line that says "closed" anywhere is exempt, so the cited refs on it pass with the closed word.
        for line, numbers in (("items 214 and 381 wait on you; item 222 closed", (214, 381)),
                              ("items 214 and 381 wait on you (closed on 11-04, still needs your word)", (214, 381))):
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_blocks(copy_repo(), report(["None new.", line]), numbers,
                                       absent=(222,) if "222" in line else (), landed=landed)

    def test_ps_red_a_cite_with_punctuation_or_bold_blocks(self):
        # Catches: a cite with a colon after the word, or bold around the word, is not read, so it passes.
        # The bold forms sit mid-line: a bold word at a line start is a report label to the shape guard, which blocks
        # the turn for its own reason and would hide whether the status check read the cite.
        cases = (("Items: 214, 381 wait on you", (214, 381)),
                 ("Waiting on you: **Items:** 214, 381 wait on you", (214, 381)),
                 ("Waiting on you: **item** 214 waits on you", (214,)))
        for line, numbers in cases:
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_blocks(copy_repo(), report(["None new.", line]), numbers, landed=landed)

    def test_ps_red_combined_option_letters_are_ruling_cites(self):
        # Catches: combined option letters (a+c, a/c, a and c) are not read as ruling cites, so a closed ruling passes.
        for line in ("item 131 a+c", "item 131 a/c", "item 131 a and c"):
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_quiet(copy_repo(), report([line]), landed)

    def test_ps_red_an_error_in_the_check_is_unknown_not_a_block(self):
        # Catches: an error inside the check (the reader raises OSError) is swallowed, so the owner gets no UNKNOWN note.
        repo = copy_repo()
        for landed in (True, False):
            with self.subTest(landed=landed):
                _, witness_out, witness_err = self.run_in_process(repo, report([WITNESS_QUESTION]), landed)
                self.assertIsNone(witness_err, "scope: the witness question raised %r" % (witness_err,))
                self.assertEqual(json.loads(witness_out).get("decision"), "block",
                                 "scope: the in-process witness question did not block, so main() did not run")
                reader, out, raised = self.run_in_process(repo, report(["Waiting on you: item 214."]), landed,
                                                          error=OSError("the waiting copy cannot be read"))
                self.assertTrue(reader.called, "scope: the cited item did not reach the reader, so no error was raised")
                self.assertIsNone(raised, "an error in the check escaped the Stop guard: %r" % (raised,))
                obj = json.loads(out) if out.strip() else {}
                self.assertNotEqual(obj.get("decision"), "block", "an error in the check blocked a cited item: landed=%s"
                                    % landed)
                self.assertIn("UNKNOWN", obj.get("systemMessage") or "",
                              "an error in the check gave no UNKNOWN systemMessage: landed=%s" % landed)

    # --- unknown: a copy that cannot be read ---

    def test_ps_red_an_unreadable_copy_is_unknown_not_a_block(self):
        # Catches: a copy that cannot be read passes with no note, so the owner is never told the status is unknown.
        # Five ways a copy can be unreadable, on a landed and an unlanded turn.
        text = report(["Waiting on you: item 214."])
        for label, repo in (
                ("no record branch", no_branch_repo()),
                ("a copy on the local record branch only", local_copy_repo()),
                ("a record branch with no waiting folder", no_folder_repo()),
                ("a record branch ref git cannot read", torn_repo()),
                ("an item file that is not JSON", corrupt_repo())):
            for landed in (True, False):
                with self.subTest(copy=label, landed=landed):
                    self.assert_unknown(repo, text, landed)

    def test_ps_red_letters_joined_by_or_or_comma_are_no_ruling_cite(self):
        # Catches: a letter list joined by "or" or "," reads as a ruling, so "item 214 a or b" passes a closed cite.
        # A letter list joins only with "+", "/" or "and".
        for line in ("item 214: pick a or b", "item 214 a or b"):
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_blocks(copy_repo(), report(["None new.", line]), (214,), landed=landed)

    def test_ps_red_a_ruling_letter_before_a_parenthetical_dash_or_option_word_passes(self):
        # Catches: a ruling letter followed by " (", an em or en dash, or a closing bold is read as no ruling, so a
        # closed item the owner has ruled on blocks. "option <letter>" counts like "pick <letter>". The bold form sits
        # mid-line: a bold word at a line start trips the report-shape guard.
        for line in ("item 109 pick a (2026-11-04 17:55 CST)",
                     "item 109 b (owner, 11-04 17:55 CST)",
                     "item 109 a (Nov 4 17:44 CST)",
                     "per item 109 option b",
                     "Choice: **item 109 b**",
                     "item 109 b — Nov 1",
                     "item 109 b – Nov 1"):
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_quiet(copy_repo(), report([line]), landed)

    # --- controls: each passes today, and each stays green after the build ---

    def test_ps_green_a_bare_cite_before_a_non_letter_parenthetical_still_blocks(self):
        # Catches: a parenthetical after a bare cite is read as a ruling, so a closed item with a note passes.
        for landed in (True, False):
            with self.subTest(landed=landed):
                self.assert_blocks(copy_repo(), report(["item 214 (waiting since Nov 4)"]), (214,), landed=landed)

    def test_ps_green_an_open_item_cite_passes(self):
        # Catches: a cite of an open item blocks, so the owner is refused a question the page still holds open.
        for landed in (True, False):
            for line in ("Waiting on you: item 365.", "Waiting on you: page item 365.", "Waiting on you: page:365."):
                with self.subTest(line=line, landed=landed):
                    self.assert_quiet(copy_repo(), report([line]), landed)

    def test_ps_green_a_ruling_cite_on_a_closed_item_passes(self):
        # Catches: a ruling cite (a ref, then an option letter, "pick <letter>", or "note" ending its clause) is read as
        # an open question, so a closed item the owner has ruled on blocks.
        for line in ("item 214 a", "item 214: b", "page item 109, pick b", "item 127, note", "(item 127 note)"):
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_quiet(copy_repo(), report([line]), landed)

    def test_ps_green_a_question_form_label_line_passes(self):
        # Catches: a question-form label line ("Based on (" or "Departs from:") is read as a plain cite and blocks.
        for line in ("- **Based on (page)** item 214 is filed, nothing waits.",
                     "Departs from: item 214 on the page, no pick.",
                     "- **Departs from:** item 214 on the page, no pick."):
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_quiet(copy_repo(), report(["None new.", line]), landed)

    def test_ps_green_a_closed_word_directly_after_a_ref_passes(self):
        # Catches: "closed" directly after a ref is read as a waiting cite, so a closed item the page says is closed blocks.
        for line in ("item 214 closed", "item 214 is closed", "item 214 (closed)"):
            for landed in (True, False):
                with self.subTest(line=line, landed=landed):
                    self.assert_quiet(copy_repo(), report([line]), landed)

    def test_ps_green_a_line_that_says_the_item_is_closed_passes(self):
        # Catches: a line that itself says the item is closed is read as a waiting cite and blocks.
        self.assert_quiet(copy_repo(), report(["item 214 is closed on the page, so nothing waits on it."]))

    def test_ps_green_a_closed_item_cited_outside_input_needed_passes(self):
        # Catches: the check reads the whole reply, so a closed item cited under Done, Deviations or Next blocks.
        text = report(["none"], done="OTHER: read item 214 and item 381 off the page",
                      deviations="none; read item 222 off the page", nxt="ship it, then read item 383 off the page")
        self.assert_quiet(copy_repo(), text)

    def test_ps_green_a_hash_number_is_no_cite(self):
        # Catches: "#214" is read as item 214, so a PR number in Input Needed blocks on a closed item of that number.
        self.assert_quiet(copy_repo(), report(["Waiting on you: #214."]))

    def test_ps_green_a_repo_with_no_waiting_page_is_not_checked(self):
        # Catches: a repo that names no waiting page is read for a copy, so a cite there blocks or gets a note.
        repo = no_page_repo()
        for landed in (True, False):
            with self.subTest(landed=landed):
                # Scope: a question in this repo gets the no-page note, so the guard reads the reply.
                scope = self.output_of(self.run_turn(report([WITNESS_QUESTION]), landed, repo), "the no-page witness")
                self.assertIn(report_guard.NO_PAGE_NOTE, scope.get("systemMessage") or "",
                              "scope: the no-page witness got no no-page note, so the guard does not reach it")
                run = self.run_turn(report(["Waiting on you: item 214."]), landed, repo)
                self.assertEqual(run.stdout.strip(), "",
                                 "a repo with no waiting page got output for a cited item: %r" % run.stdout[:300])

    def test_ps_green_no_cite_writes_no_unknown_note_for_an_unreadable_copy(self):
        # Catches: an unreadable copy is reported UNKNOWN for an Input Needed item that cites nothing, though no read ran.
        repo = corrupt_repo()
        for landed in (True, False):
            with self.subTest(landed=landed):
                self.assert_quiet(repo, report(["None new."]), landed)

    # --- cost, in this process: the reader is patched, so a call is seen whether or not git runs ---

    def test_ps_green_a_report_that_cites_no_item_reads_no_status(self):
        # Catches: every report reads the waiting copy, a git call, though a report with no item cite needs none.
        self.assertEqual(os.path.realpath(feedback_guard.__file__),
                         os.path.realpath(os.path.join(HOOKS, "feedback_guard.py")),
                         "scope: feedback_guard is not this worktree's module, so the patch misses the guard's reader")
        self.assertEqual(os.path.realpath(report_guard.__file__), os.path.realpath(os.path.join(HERE, "report_guard.py")),
                         "scope: report_guard is not this worktree's module")
        repo = copy_repo()
        for landed in (True, False):
            for lines in (["none"], ["Waiting on the page writer for the copy."], ["None new.", "- Nothing else is open."]):
                with self.subTest(lines=lines, landed=landed):
                    _, witness_out, _ = self.run_in_process(repo, report([WITNESS_QUESTION]), landed, {})
                    self.assertEqual(json.loads(witness_out).get("decision"), "block",
                                     "scope: the in-process witness question did not block, so main() did not run")
                    reader, _, _ = self.run_in_process(repo, report(lines), landed, {})
                    self.assertFalse(reader.called, "a report that cites no item read the waiting copy: %r" % lines)

    def test_ps_red_a_cite_in_input_needed_reads_the_waiting_copy(self):
        # Catches: a report that cites an item never reads the waiting copy, so the check cannot see the closed item.
        repo = copy_repo()
        for landed in (True, False):
            with self.subTest(landed=landed):
                _, witness_out, _ = self.run_in_process(repo, report([WITNESS_QUESTION]), landed, {})
                self.assertEqual(json.loads(witness_out).get("decision"), "block",
                                 "scope: the in-process witness question did not block, so main() did not run")
                reader, _, _ = self.run_in_process(repo, report(["Waiting on you: item 214."]), landed, {})
                self.assertTrue(reader.called, "a cite of item 214 in Input Needed did not read the waiting copy")
                self.assertEqual(reader.call_args[0][0], os.path.realpath(repo),
                                 "the waiting copy was read from another repo")


if __name__ == "__main__":
    unittest.main()
