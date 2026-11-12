#!/usr/bin/env python3
"""The report guard refuses an Input Needed line that cites a closed waiting-page item.

A coordinator listed items 214, 381, 383 and 222 to the owner as open, and all four were closed. The report
guard (report_guard.py, a Stop hook) reads each cited page item's status from the waiting copy on origin/<record
branch>, through the one waiting-copy reader (feedback_guard's Homes.filed_numbers, extended to n -> status), and
refuses an Input Needed line that cites a closed item. The rules the cases pin:

- Cite forms, in the Input Needed section only: "item 214", "page item 214", "items 214, 381 and 383",
  "items 214 or 381", "items 214/381", "items 214-216" (both ends), "Items: 214, 381", "**Items:** 214",
  "**Items**: 214", "item(s) 214", "item **214**", "items:" then a bullet list whose bullets may carry text
  ("> - 214: pick a or b"), a label such as "Items waiting on you:" before such a list, a dash-bulleted label
  ("- Items waiting on you:") with its sub-bullets, numbers that are sub-bullets of a label bullet ("> - waiting"
  then ">   - 214"), "Cockpit item 214", "item-214", "page-item-214", "Cockpit item-214", "items 214-216",
  "items 214–216" (en dash), "items 214 to 216", "items 214 through 216" (both ends), "items 214; 381",
  "items 214 + 381", "item 214 a", "item 1 of 3" (cites 1). Not in Done or Next, not inside backticks or quotes, not PR numbers
  ("PR" or "#" before the number), not an ISO date after "item", not a bare number, not a list marker
  ("> 1. 214" cites 214).
- Not a cite, though a number follows the item: a count ("214 and 5 others", "381, 2 of which"), a clock time,
  a percent, an hour count, an ordinal, a fraction ("11/10"), a dash option ("214 - 3 options"), a blockquoted
  bullet option after the item ("item 214" then "> - 3 options"), a count after "to", ";" or "+" ("214 to 3
  options", "214; 3 tests", "214 + 3 more"), and a sub-bullet under a numbered bullet, which is the item's own text
  ("- 214 pick" then "  - 1 a: ship"), plain or under a label.
- A cited item whose status is `closed` in the copy refuses the Stop. The refusal states that each closed item
  reads closed in the waiting copy, and names no step for the session.
- An open or missing item passes. A same-turn ArtifactData read of collection `items` that shows the item open
  skips the copy for that item. A same-turn read that shows it closed refuses the Stop, whether the copy holds it
  open or cannot be read. A read in an earlier turn does not count.
- Fails open: no record branch, no items folder, an item file that is not a JSON object, a git error. No refusal,
  and a systemMessage that says "not checked". The guard never raises.
- A repo with no waiting page runs no check and reads no copy. One copy read per Stop.

Each refusal case is red on a guard with no such check, where its Stop passes. A control case pins what must
stay passing, and it passes on that code too. The record-branch repo, the page URL and the ArtifactData read
output come from hooks/test_feedback_inbox.py. The Stop runner and the transcript records come from
lint/test_report_guard.py. Run with:

    python3 lint/test_report_guard_closed_item.py -v
"""
import itertools
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import test_report_guard as trg  # noqa: E402  the Stop runner, the transcript records and the isolation (one home)
import test_feedback_inbox as tfi  # noqa: E402  the record-branch repo, the page URL and the read output (one home)

RECORD_BRANCH = tfi.RECORD_BRANCH
DONE = "> **Done** BUILT abc123"
NEXT = "> **Next** wait"
COMMIT = "git commit -m step"
BAD_ITEM = "{ not json"
_TRANSCRIPTS = itertools.count(1)

# (n, status) per waiting copy item. Each set has its own repo key, so a repo is built once per set.
CLOSED_214 = ((214, "closed"), (381, "open"), (383, "open"), (222, "open"))
CLOSED_381 = ((214, "open"), (381, "closed"), (383, "open"))
CLOSED_ALL = ((214, "closed"), (381, "closed"), (383, "closed"), (222, "closed"))
OPEN_214 = ((214, "open"), (381, "open"))
PREFIX_2140 = ((2140, "closed"), (214, "open"))
FORTY = ((214, "closed"),) + tuple((100 + i, "open") for i in range(39))
CLOSED_RANGE = ((214, "closed"), (215, "open"), (216, "closed"))  # 215 is the middle of the range, an accepted gap
CLOSED_2 = ((2, "closed"), (214, "open"))
DATE_PARTS = ((2026, "closed"), (10, "closed"), (11, "closed"))  # each part of an ISO date closed
CLOSED_PAIR = ((214, "closed"), (381, "closed"), (383, "open"))
CLOSED_1_OF_3 = ((1, "closed"), (3, "open"))  # 3 stays open, so the M of "item 1 of 3" is not pinned
NUMBERED = ((1, "closed"), (2, "closed"), (214, "closed"), (381, "closed"))
SEVEN_NINE = ((7, "closed"), (9, "closed"))
# Every closed number a false cite could read as. The copy holds each one closed, so a false cite is refused by name.
# 381 is closed too: "items 214 and 381, 2 of which" cites it, so a list that stops at "and" is caught.
FALSE_CITES = ((1, "closed"), (2, "closed"), (3, "closed"), (5, "closed"), (10, "closed"), (11, "closed"),
               (24, "closed"), (214, "closed"), (381, "closed"))
FALSE_NUMS = (1, 2, 3, 5, 10, 11, 24)


def setUpModule():
    trg.setUpModule()  # the run folder, the model stub and CLAUDE_CONFIG_DIR, as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()
    shutil.rmtree(tfi.ROOT, ignore_errors=True)  # the repos these cases build live under the feedback fixture's folder


def status_files(items):
    """{path: text} for a waiting copy: one waiting/items/n<n>.json per (n, status), with the numeric field n and the
    field status, as the waiting page writes an item."""
    return {"waiting/items/n%d.json" % n: json.dumps({"id": "item-%d" % n, "n": n, "status": status})
            for n, status in items}


def copy_repo(key, items, **kw):
    """A waiting page whose record branch holds the copy `items`. The branch's remote-tracking ref holds it."""
    return tfi.record_repo(key, status_files(items), **kw)


def copy_status(root, n):
    """The status the record branch's copy holds for item n. The cases read it with git before they assert, so a
    refusal is judged against a fixture that holds the item closed."""
    text = tfi.git(root, "show", "refs/remotes/origin/%s:waiting/items/n%d.json" % (RECORD_BRANCH, n))
    return json.loads(text)["status"]


def copy_reads(trace):
    """How many git grep calls read the waiting copy's items folder, in a GIT_TRACE file. Missing file: none."""
    try:
        with open(trace, encoding="utf-8", errors="replace") as f:
            return sum(1 for ln in f if "grep" in ln and "waiting/items/" in ln)
    except FileNotFoundError:
        return 0


def artifact_read(n, status):
    """An ArtifactData get of item n in collection items, and the result the page returns: the document that holds
    it. The read and its result pair by tool_use_id."""
    use_id = "rb%d" % n
    use = trg.tool_use_msg("ArtifactData", tfi.tool_input("get", collection="items", doc_id="n%d" % n), id_=use_id)
    doc = {"id": "item-%d" % n, "n": n, "status": status}
    return [use, trg.tool_result_msg(use_id, tfi.response_of([("n%d" % n, doc)]))]


def report(input_needed, done=DONE, nxt=NEXT):
    """A report whose Input Needed item holds `input_needed`. It holds no question, pick or option."""
    return "\n".join([done, "> **Input Needed** " + input_needed, nxt])


class ClosedItemFixture(unittest.TestCase):
    """The Stop runner of these cases: one transcript and one repo per Stop. A case reads its own stdout."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg._ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        self.cfg = os.path.join(self.run_dir, "cfg")
        self.home = os.path.join(self.run_dir, "home")
        os.makedirs(self.cfg)
        os.makedirs(self.home)

    def stop(self, records, repo, trace=None):
        """Runs the report guard as a Stop in `repo` over `records`. Returns the parsed stdout, or None when it printed
        none. `trace` is a GIT_TRACE file the guard's git calls append to."""
        name = "transcript-%d.jsonl" % next(_TRANSCRIPTS)
        path = trg.write_transcript(records, self.run_dir, name=name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": repo}
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        if trace:
            env["GIT_TRACE"] = trace
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0, "the guard exited %d: %s" % (run.returncode, run.stderr))
        self.assertNotIn("Traceback", run.stderr, "the guard raised instead of failing open")
        return json.loads(run.stdout) if run.stdout.strip() else None

    def turn(self, reply, *calls):
        """One owner turn: the owner's message, the records of its calls, then the reply."""
        return [trg.human("look at the open items"), *calls, trg.assistant_text(reply)]

    def assert_refused(self, out, closed, what, source="waiting copy"):
        """A block that names each closed item, then states the fact: the item reads closed in the waiting copy, or in
        this turn's read (`source`). The numbers come first, so a cite the guard misses fails on the number, not on
        the wording."""
        self.assertIsNotNone(out, "%s: the Stop passed, so the closed item was not refused" % what)
        self.assertEqual(out.get("decision"), "block", "%s: no block: %r" % (what, out))
        reason = out.get("reason", "")
        for n in closed:
            self.assertRegex(reason, r"(?<!\d)%d(?!\d)" % n, "%s: the refusal does not name closed item %d" % (what, n))
        self.assertIn("closed", reason, "%s: the refusal does not say closed" % what)
        self.assertIn(source, reason, "%s: the refusal does not say %r shows it" % (what, source))
        self.assertNotIn("get or query", reason, "%s: the refusal names a step (get or query)" % what)
        self.assertNotIn("is read before", reason, "%s: the refusal names a step (is read before)" % what)

    def assert_cites_only(self, out, cited, what):
        """A refusal that names each cited closed item and no other number in FALSE_NUMS, the numbers a false cite
        reads as. Each of those is closed in the copy, so a false cite would be named."""
        self.assert_refused(out, cited, what)
        reason = out.get("reason", "")
        for n in FALSE_NUMS:
            if n not in cited:
                self.assertNotRegex(reason, r"(?<!\d)%d(?!\d)" % n,
                                    "%s: the refusal names %d, which the text does not cite" % (what, n))

    def assert_passes(self, out, what):
        self.assertIsNone(out, "%s: expected no refusal and no note, got %r" % (what, out))

    def assert_not_checked(self, out, what):
        """No refusal, and a systemMessage that says the check did not run."""
        self.assertIsNotNone(out, "%s: no systemMessage, so the check did not say it was not checked" % what)
        self.assertNotEqual(out.get("decision"), "block", "%s: a block on a check that could not run: %r" % (what, out))
        self.assertIn("not checked", out.get("systemMessage", ""),
                      "%s: the systemMessage does not say not checked: %r" % (what, out))


class ClosedItemRefusalTests(ClosedItemFixture):
    """Each of these Stops refuses a cited item that the waiting copy shows closed."""

    def test_item_form_refuses_a_closed_item(self):
        # Catches: "item 214" in Input Needed passing while the page holds item 214 closed.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("item 214 is open.")), repo)
        self.assert_refused(out, [214], "item 214 cited in Input Needed")

    def test_page_item_form_refuses_a_closed_item(self):
        # Catches: the "page item 214" form passing as no cite.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("page item 214 is open.")), repo)
        self.assert_refused(out, [214], "page item 214 cited in Input Needed")

    def test_cockpit_item_form_refuses_a_closed_item(self):
        # Catches: the "Cockpit item 214" form passing as no cite.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("Cockpit item 214 is open.")), repo)
        self.assert_refused(out, [214], "Cockpit item 214 cited in Input Needed")

    def test_letter_suffix_form_refuses_a_closed_item(self):
        # Catches: "item 214 a" with a letter after the number passing as no cite.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("item 214 a is open.")), repo)
        self.assert_refused(out, [214], "item 214 a cited in Input Needed")

    def test_items_list_refuses_the_closed_item_in_it(self):
        # Catches: a list "items 214, 381 and 383" read as its first number only, so 381 closed passes.
        repo = copy_repo("closed381", CLOSED_381)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214, 381 and 383 are open.")), repo)
        self.assert_refused(out, [381], "items 214, 381 and 383 cited in Input Needed, 381 closed")

    def test_coordinator_case_names_all_four_closed_items(self):
        # Catches: the coordinator's case: items 214, 381, 383 and 222 listed open while all four are closed.
        repo = copy_repo("closed-all", CLOSED_ALL)
        for n in (214, 381, 383, 222):
            self.assertEqual(copy_status(repo, n), "closed", "the fixture copy must hold item %d closed" % n)
        out = self.stop(self.turn(report("items 214, 381, 383 and 222 are open.")), repo)
        self.assert_refused(out, [214, 381, 383, 222], "the four items listed open, all closed")

    def test_apostrophe_and_comment_openers_do_not_hide_a_cite(self):
        # Catches: a lone apostrophe or a comment opener in the text masking the cite that follows it.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("The owner's item 214 is closed. See /* note */ and // here.")), repo)
        self.assert_refused(out, [214], "an apostrophe and comment openers beside item 214")

    def test_full_size_copy_refuses_the_closed_item(self):
        # Catches: a copy of 40 items hiding the closed one among them, the full-size state of the copy.
        repo = copy_repo("forty", FORTY)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("item 214 is open.")), repo)
        self.assert_refused(out, [214], "item 214 cited, in a copy of 40 items")

    def test_same_turn_read_back_open_skips_only_its_item(self):
        # Catches: a same-turn read that shows item 214 open also clearing item 381, which the copy holds closed.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214 and 381 are open."), *artifact_read(214, "open")), repo)
        self.assert_refused(out, [381], "items 214 and 381, 214 read open this turn, 381 closed in the copy")

    def test_read_back_from_an_earlier_turn_does_not_skip_the_copy(self):
        # Catches: a read in an earlier turn clearing a cite in this one, including a turn slice that starts at the
        # first human message. The read is in the turn before the last human message, so only the copy may decide.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        records = [trg.human("look at the open items"), *artifact_read(214, "open"),
                   trg.assistant_text("Here are the items."), trg.human("and item 214?"),
                   trg.assistant_text(report("item 214 is open."))]
        out = self.stop(records, repo)
        self.assert_refused(out, [214], "item 214 cited, read open in an earlier turn only")
        self.assertNotIn("read this turn", out.get("reason", ""),
                         "the refusal took the earlier turn's read as one of this turn's")

    def test_landed_turn_refuses_a_closed_item_too(self):
        # Catches: the check run only on an unlanded turn, so a report after a commit passes a closed cite.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        commit = [trg.tool_use_msg("Bash", {"command": COMMIT}, id_="g1"),
                  trg.tool_result_msg("g1", "[main abc123] step")]
        out = self.stop(self.turn(report("item 214 is open."), *commit), repo)
        self.assert_refused(out, [214], "item 214 cited in a landed turn")


class ClosedItemReadClosedTests(ClosedItemFixture):
    """A same-turn ArtifactData read that shows a cited item closed refuses the Stop. The copy either holds the item
    open or cannot be read, so the read alone decides that item. Each refusal names the read as its source."""

    def test_read_closed_refuses_when_the_copy_holds_it_open(self):
        # Catches: a same-turn read that shows item 214 closed ignored, so the copy's open item 214 passes the Stop.
        repo = copy_repo("open214", OPEN_214)
        self.assertEqual(copy_status(repo, 214), "open", "the fixture copy must hold item 214 open")
        out = self.stop(self.turn(report("item 214 is open."), *artifact_read(214, "closed")), repo)
        self.assert_refused(out, [214], "item 214 read closed this turn, the copy holds it open", source="read this turn")

    def test_read_closed_refuses_when_the_copy_is_unreadable(self):
        # Catches: a same-turn read that shows item 214 closed ignored when the copy cannot be read, so the Stop passes.
        repo = copy_repo("torn-ref", CLOSED_214, torn=True)
        out = self.stop(self.turn(report("item 214 is open."), *artifact_read(214, "closed")), repo)
        self.assert_refused(out, [214], "item 214 read closed this turn, the copy unreadable", source="read this turn")

    def test_read_closed_and_copy_closed_items_are_both_named(self):
        # Catches: a refusal that drops the read's closed item 214, or the copy's closed item 381, when both are cited.
        repo = copy_repo("closed381", CLOSED_381)  # 214 open, 381 closed, 383 open
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214 and 381 are open."), *artifact_read(214, "closed")), repo)
        self.assert_refused(out, [214, 381], "items 214 and 381: 214 read closed this turn, 381 closed in the copy",
                            source="read this turn")
        self.assertIn("waiting copy", out.get("reason", ""), "the refusal does not name the copy's closed item 381")


class ClosedItemCiteFormTests(ClosedItemFixture):
    """Cite forms. Each one must name the page items it cites, and a closed one among them refuses the Stop. A case
    asserts every number its form cites, so a guard that reads only the first number fails on the second."""

    def test_or_list_names_every_item(self):
        # Catches: "items 214 or 381" read as its first number only, so 381 closed passes.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214 or 381 are open.")), repo)
        self.assert_refused(out, [214, 381], "items 214 or 381, both closed")

    def test_slash_list_names_every_item(self):
        # Catches: "items 214/381" read as its first number only.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214/381 are open.")), repo)
        self.assert_refused(out, [214, 381], "items 214/381, both closed")

    def test_or_before_the_last_item_names_it(self):
        # Catches: "items 214, 381, or 383" with the "or" before the last item, so 383 closed passes.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 383), "closed", "the fixture copy must hold item 383 closed")
        out = self.stop(self.turn(report("items 214, 381, or 383 are open.")), repo)
        self.assert_refused(out, [214, 381, 383], "items 214, 381, or 383, all closed")

    def test_parenthetical_does_not_end_the_list(self):
        # Catches: "items 214 (closed), 381 and 383" read as item 214 alone, so 381 and 383 closed pass.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214 (closed), 381 and 383 are open.")), repo)
        self.assert_refused(out, [214, 381, 383], "items 214 (closed), 381 and 383, all closed")

    def test_range_names_both_ends(self):
        # Catches: "items 214-216" read as item 214 alone, so 216 closed passes. The middle, 215, is an accepted gap:
        # it is not pinned here.
        repo = copy_repo("closed-range", CLOSED_RANGE)
        self.assertEqual(copy_status(repo, 216), "closed", "the fixture copy must hold item 216 closed")
        out = self.stop(self.turn(report("items 214-216 are open.")), repo)
        self.assert_refused(out, [214, 216], "items 214-216, 214 and 216 closed")

    def test_colon_after_items_names_every_item(self):
        # Catches: "Items: 214, 381" with a colon after the word, so 381 closed passes.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("Items: 214, 381 are open.")), repo)
        self.assert_refused(out, [214, 381], "Items: 214, 381, both closed")

    def test_parenthesized_plural_names_the_item(self):
        # Catches: "item(s) 214" read as no cite, so item 214 closed passes.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("item(s) 214 is open.")), repo)
        self.assert_refused(out, [214], "item(s) 214 cited")

    def test_bold_number_names_the_item(self):
        # Catches: "item **214**" read as no cite, so item 214 closed passes.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("item **214** is open.")), repo)
        self.assert_refused(out, [214], "item **214** cited")

    def test_page_dash_item_names_the_item(self):
        # Catches: "page-item 214" read as no cite, because the hyphen before "item" blocks the match.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("page-item 214 is open.")), repo)
        self.assert_refused(out, [214], "page-item 214 cited")

    def test_bullet_list_after_items_colon_names_every_item(self):
        # Catches: "items:" followed by a bullet list of numbers read as no cite, so 381 closed passes. The bullets
        # are blockquoted, as a report's lines are, so the Input Needed item holds them.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items:\n> - 214\n> - 381")), repo)
        self.assert_refused(out, [214, 381], "items: then a bullet list of 214 and 381, both closed")

    def test_item_2_in_a_plan_is_a_cite(self):
        # Catches: "the item 2 in the diff plan" passing as no cite. It is a cite by design, a low false alarm.
        repo = copy_repo("closed-2", CLOSED_2)
        self.assertEqual(copy_status(repo, 2), "closed", "the fixture copy must hold item 2 closed")
        out = self.stop(self.turn(report("the item 2 in the diff plan is open.")), repo)
        self.assert_refused(out, [2], "the item 2 in the diff plan, item 2 closed")

    def test_item_date_is_no_cite(self):
        # Catches: an ISO date after "item" read as item 2026 (and its month or day, in a range), so a closed 2026
        # refuses the Stop.
        # Old code reads 2026 as a cite, so this case is red there.
        repo = copy_repo("date-parts", DATE_PARTS)
        self.assertEqual(copy_status(repo, 2026), "closed", "the fixture copy must hold item 2026 closed")
        self.assert_passes(self.stop(self.turn(report("item 2026-11-10 is open.")), repo),
                           "item 2026-11-10, with 2026, 10 and 11 closed in the copy")

    def test_bold_label_colon_names_every_item(self):
        # Catches: "**Items:** 214, 381" with the colon inside the bold, so no cite is read and item 214 closed passes.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("**Items:** 214, 381 are open.")), repo)
        self.assert_refused(out, [214, 381], "**Items:** 214, 381, both closed")

    def test_bold_label_colon_after_bold_names_every_item(self):
        # Catches: "**Items**: 214, 381" with the colon after the bold, so no cite is read and item 214 closed passes.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("**Items**: 214, 381 are open.")), repo)
        self.assert_refused(out, [214, 381], "**Items**: 214, 381, both closed")

    def test_bold_label_bullet_list_names_every_item(self):
        # Catches: "**Items:**" then a bullet list read as no cite, so item 214 closed passes.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("**Items:**\n> - 214\n> - 381")), repo)
        self.assert_refused(out, [214, 381], "**Items:** then a bullet list of 214 and 381, both closed")

    def test_bullet_with_text_after_its_number_names_every_item(self):
        # Catches: a bullet's text after its number ("214: pick a or b") ending the list, so 381 closed passes.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("Items:\n> - 214: pick a or b\n> - 381: pick c")), repo)
        self.assert_refused(out, [214, 381], "Items: then bullets with text after 214 and 381, both closed")

    def test_labelled_bullets_name_every_item(self):
        # Catches: a list under a label such as "Items waiting on you:" read as no cite, so item 214 closed passes.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("Items waiting on you:\n> - 214: pick\n> - 381: pick")), repo)
        self.assert_refused(out, [214, 381], "Items waiting on you: then bullets of 214 and 381, both closed")

    def test_numbered_list_names_the_items_not_the_markers(self):
        # Catches: the list markers "1." and "2." read as cites, and items 214 and 381 after them read as no cite.
        repo = copy_repo("numbered-list", NUMBERED)
        self.assertEqual(copy_status(repo, 1), "closed", "the fixture copy must hold item 1 closed")
        out = self.stop(self.turn(report("items:\n> 1. 214\n> 2. 381")), repo)
        self.assert_cites_only(out, [214, 381], "items: then a numbered list of 214 and 381, 1 and 2 closed")

    def test_items_list_with_and_names_all_three(self):
        # Catches: "items 214, 381 and 383" read as fewer than its three items.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 383), "closed", "the fixture copy must hold item 383 closed")
        out = self.stop(self.turn(report("items 214, 381 and 383 are open.")), repo)
        self.assert_refused(out, [214, 381, 383], "items 214, 381 and 383, all closed")

    def test_two_item_list_names_both(self):
        # Catches: "items 7 and 9" read as item 7 alone, so item 9 closed passes.
        repo = copy_repo("closed-7-9", SEVEN_NINE)
        self.assertEqual(copy_status(repo, 9), "closed", "the fixture copy must hold item 9 closed")
        out = self.stop(self.turn(report("items 7 and 9 are open.")), repo)
        self.assert_refused(out, [7, 9], "items 7 and 9, both closed")

    def test_item_n_of_m_names_item_n(self):
        # Catches: "Item 1 of 3" read as no cite. Item 1 is the cite; the 3 is not pinned here (a note).
        repo = copy_repo("closed-1-of-3", CLOSED_1_OF_3)
        self.assertEqual(copy_status(repo, 1), "closed", "the fixture copy must hold item 1 closed")
        out = self.stop(self.turn(report("Item 1 of 3 needs your pick.")), repo)
        self.assert_refused(out, [1], "Item 1 of 3, item 1 closed")

    def test_en_dash_range_names_both_ends(self):
        # Catches: "items 214–216" with an en dash read as item 214 alone, so 216 closed passes. The middle, 215, is
        # not pinned, as with the hyphen range.
        repo = copy_repo("closed-range", CLOSED_RANGE)
        self.assertEqual(copy_status(repo, 216), "closed", "the fixture copy must hold item 216 closed")
        out = self.stop(self.turn(report("items 214–216 are open.")), repo)
        self.assert_refused(out, [214, 216], "items 214 en dash 216, 214 and 216 closed")

    def test_to_range_names_both_ends(self):
        # Catches: "items 214 to 216" read as item 214 alone, so 216 closed passes. The middle is not pinned.
        repo = copy_repo("closed-range", CLOSED_RANGE)
        self.assertEqual(copy_status(repo, 216), "closed", "the fixture copy must hold item 216 closed")
        out = self.stop(self.turn(report("items 214 to 216 are open.")), repo)
        self.assert_refused(out, [214, 216], "items 214 to 216, 214 and 216 closed")

    def test_through_range_names_both_ends(self):
        # Catches: "items 214 through 216" read as item 214 alone, so 216 closed passes. The middle is not pinned.
        repo = copy_repo("closed-range", CLOSED_RANGE)
        self.assertEqual(copy_status(repo, 216), "closed", "the fixture copy must hold item 216 closed")
        out = self.stop(self.turn(report("items 214 through 216 are open.")), repo)
        self.assert_refused(out, [214, 216], "items 214 through 216, 214 and 216 closed")

    def test_semicolon_list_names_every_item(self):
        # Catches: "items 214; 381" read as item 214 alone, so 381 closed passes.
        repo = copy_repo("closed-pair", CLOSED_PAIR)  # 214 closed, 381 closed, 383 open
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214; 381 are open.")), repo)
        self.assert_refused(out, [214, 381], "items 214; 381, both closed")

    def test_plus_list_names_every_item(self):
        # Catches: "items 214 + 381" read as item 214 alone, so 381 closed passes.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items 214 + 381 are open.")), repo)
        self.assert_refused(out, [214, 381], "items 214 + 381, both closed")

    def test_hyphen_item_form_names_the_item(self):
        # Catches: "item-214" read as no cite, because the hyphen after the word blocks the number.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("item-214 is open.")), repo)
        self.assert_refused(out, [214], "item-214 cited")

    def test_page_hyphen_item_form_names_the_item(self):
        # Catches: "page-item-214" read as no cite, because the hyphen after the word blocks the number.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("page-item-214 is open.")), repo)
        self.assert_refused(out, [214], "page-item-214 cited")

    def test_cockpit_hyphen_item_form_names_the_item(self):
        # Catches: "Cockpit item-214" read as no cite, because the hyphen after the word blocks the number.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("Cockpit item-214 is open.")), repo)
        self.assert_refused(out, [214], "Cockpit item-214 cited")

    def test_dash_label_bullets_name_every_item(self):
        # Catches: a list under a dash-bulleted label ("- Items waiting on you:") read as no cite, so 214 and 381 closed
        # pass. The sub-bullets are the list.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("- Items waiting on you:\n>   - 214: pick\n>   - 381: pick")), repo)
        self.assert_refused(out, [214, 381], "- Items waiting on you: then sub-bullets of 214 and 381, both closed")

    def test_numbers_nested_under_a_label_bullet_name_every_item(self):
        # Catches: numbers that are sub-bullets of a label bullet ("- waiting") read as no cite, so 214 and 381 closed
        # pass. The label holds no number, so its sub-bullets are the list, not the item's own text.
        repo = copy_repo("closed-pair", CLOSED_PAIR)
        self.assertEqual(copy_status(repo, 381), "closed", "the fixture copy must hold item 381 closed")
        out = self.stop(self.turn(report("items:\n> - waiting\n>   - 214\n>   - 381")), repo)
        self.assert_refused(out, [214, 381], "items: then a label bullet with sub-bullets 214 and 381, both closed")


class ClosedItemFalseCiteTests(ClosedItemFixture):
    """A number in the text that is no page item is no cite. Each text refuses on its real item alone, with the false
    number closed in the copy, so a false cite would name it in the refusal."""

    def check_false_cite(self, text, false_n, what, cited=(214,)):
        repo = copy_repo("false-cites", FALSE_CITES)
        self.assertEqual(copy_status(repo, false_n), "closed", "the fixture copy must hold item %d closed" % false_n)
        out = self.stop(self.turn(report(text)), repo)
        self.assert_cites_only(out, list(cited), what)

    def test_count_after_list_is_no_cite(self):
        # Catches: "381, 2 of which" read as a list that cites item 2. Items 214 and 381 are the cites.
        self.check_false_cite("items 214 and 381, 2 of which are open.", 2, "items 214 and 381, 2 of which are open",
                              cited=(214, 381))

    def test_count_after_and_is_no_cite(self):
        # Catches: "and 5 others" read as a list that cites item 5.
        self.check_false_cite("item 214 and 5 others.", 5, "item 214 and 5 others")

    def test_more_after_and_is_no_cite(self):
        # Catches: "and 3 more tests" read as a list that cites item 3.
        self.check_false_cite("item 214 and 3 more tests.", 3, "item 214 and 3 more tests")

    def test_dash_option_is_no_cite(self):
        # Catches: "214 - 3 options" read as a range that cites item 3.
        self.check_false_cite("item 214 - 3 options.", 3, "item 214 - 3 options")

    def test_clock_time_is_no_cite(self):
        # Catches: the hour of "10:30 CST" read as a list item that cites item 10.
        self.check_false_cite("item 214, 10:30 CST.", 10, "item 214, 10:30 CST")

    def test_fraction_is_no_cite(self):
        # Catches: "11/10" read as cites of items 11 and 10.
        self.check_false_cite("item 214 and 11/10.", 11, "item 214 and 11/10")

    def test_ordinal_is_no_cite(self):
        # Catches: "3rd" read as item 3.
        self.check_false_cite("item 214 or 3rd.", 3, "item 214 or 3rd")

    def test_percent_is_no_cite(self):
        # Catches: "5% done" read as item 5.
        self.check_false_cite("item 214, 5% done.", 5, "item 214, 5% done")

    def test_hour_count_is_no_cite(self):
        # Catches: "24h wait" read as item 24.
        self.check_false_cite("item 214 and 24h wait.", 24, "item 214 and 24h wait")

    def test_blockquoted_bullet_option_after_item_is_no_cite(self):
        # Catches: the same bullet, blockquoted, read as a cite of item 3.
        self.check_false_cite("item 214\n> - 3 options", 3, "item 214, then a blockquoted bullet '> - 3 options'")

    def test_option_bullet_after_a_pick_is_no_cite(self):
        # Catches: the option bullet "- 1 a: ship" under "Pick for item 214" read as a cite of item 1.
        self.check_false_cite("Pick for item 214\n> - 1 a: ship", 1, "Pick for item 214, then a bullet '- 1 a: ship'")

    def test_sub_bullet_under_a_numbered_bullet_is_no_cite(self):
        # Catches: the sub-bullet "- 1 a: ship" under the numbered bullet "- 214 pick" read as a cite of item 1. A
        # number under a numbered bullet is that item's own text, so only 214 is cited.
        self.check_false_cite("items:\n> - 214 pick\n>   - 1 a: ship", 1,
                              "items: then '- 214 pick' and its sub-bullet '- 1 a: ship'")

    def test_sub_bullet_under_a_numbered_bullet_in_a_label_list_is_no_cite(self):
        # Catches: the same sub-bullet read as a cite of item 1 when the list sits under "Items waiting on you:".
        self.check_false_cite("Items waiting on you:\n> - 214 pick\n>   - 1 a: ship", 1,
                              "Items waiting on you: then '- 214 pick' and its sub-bullet '- 1 a: ship'")

    def test_count_after_to_is_no_cite(self):
        # Catches: "to 3 options" read as a range that cites item 3.
        self.check_false_cite("item 214 to 3 options.", 3, "item 214 to 3 options")

    def test_count_after_semicolon_is_no_cite(self):
        # Catches: "; 3 tests" read as a list that cites item 3.
        self.check_false_cite("items 214; 3 tests.", 3, "items 214; 3 tests")

    def test_count_after_plus_is_no_cite(self):
        # Catches: "+ 3 more" read as a list that cites item 3.
        self.check_false_cite("items 214 + 3 more.", 3, "items 214 + 3 more")


class ClosedItemPassTests(ClosedItemFixture):
    """Controls: what must stay passing. Each one passes on a guard with no such check, and on one with it."""

    def test_open_item_passes(self):
        # Catches: an open item refused, which would ask the owner about what is still open.
        repo = copy_repo("open214", OPEN_214)
        self.assertEqual(copy_status(repo, 214), "open", "the fixture copy must hold item 214 open")
        self.assert_passes(self.stop(self.turn(report("item 214 is open.")), repo), "item 214 open")

    def test_missing_item_passes(self):
        # Catches: an item the copy does not hold refused as closed.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        self.assert_passes(self.stop(self.turn(report("item 999 is open.")), repo), "item 999 not in the copy")

    def test_longer_number_is_not_the_closed_item(self):
        # Catches: a prefix match, where item 214 matches item 2140, or item 2140 matches item 214.
        repo = copy_repo("prefix2140", PREFIX_2140)
        self.assertEqual(copy_status(repo, 2140), "closed", "the fixture copy must hold item 2140 closed")
        self.assert_passes(self.stop(self.turn(report("item 214 is open.")), repo), "item 214, 2140 closed")
        repo = copy_repo("closed214", CLOSED_214)
        self.assert_passes(self.stop(self.turn(report("item 2140 is open.")), repo), "item 2140, 214 closed")

    def test_pr_numbers_are_not_cites(self):
        # Catches: a PR number read as a page item, so a closed item number used as a PR number is refused.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        for line in ("PR 214 is open.", "#214 is open.", "PR #214 is open."):
            with self.subTest(line=line):
                self.assert_passes(self.stop(self.turn(report(line)), repo), "%r" % line)

    def test_closed_item_in_done_or_next_passes(self):
        # Catches: a cite outside Input Needed refused. The Input Needed item is "none", so only Done and Next hold it.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        reply = "\n".join(["> **Done** OTHER item 214 is closed.", "> **Input Needed** none",
                           "> **Next** item 214 is closed, so wait."])
        self.assert_passes(self.stop(self.turn(reply), repo), "item 214 in Done and Next")

    def test_quoted_and_backticked_cites_pass(self):
        # Catches: a cite inside backticks or quotes refused. The brief says those are not cites.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        for line in ("`item 214` is open.", "\"item 214\" is open."):
            with self.subTest(line=line):
                self.assert_passes(self.stop(self.turn(report(line)), repo), "%r" % line)

    def test_bare_number_is_no_cite(self):
        # Catches: a bare number read as an item cite. The cite forms are the ones the step names, and a bare number
        # is not one of them.
        repo = copy_repo("closed214", CLOSED_214)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        self.assert_passes(self.stop(self.turn(report("214 is open.")), repo), "a bare 214")

    def test_read_back_open_with_only_its_item_cited_passes(self):
        # Catches: a same-turn read that shows item 214 open not skipping the copy for item 214.
        repo = copy_repo("closed-all", CLOSED_ALL)
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        out = self.stop(self.turn(report("item 214 is open."), *artifact_read(214, "open")), repo)
        self.assert_passes(out, "item 214 read open this turn, the copy holds it closed")

    def test_repo_with_no_waiting_page_checks_nothing(self):
        # Catches: a repo that names no waiting page checked against a copy it does not have.
        repo = tfi.record_repo("no-page", status_files(CLOSED_214), extras=json.dumps({"kinds": {}}))
        self.assertEqual(copy_status(repo, 214), "closed", "the fixture copy must hold item 214 closed")
        trace = os.path.join(self.run_dir, "no-page.trace")
        out = self.stop(self.turn(report("item 214 is open.")), repo, trace=trace)
        self.assert_passes(out, "a repo with no waiting page, item 214 closed on its branch")
        self.assertEqual(copy_reads(trace), 0, "a repo with no waiting page read the waiting copy")


class ClosedItemBlockNoteTests(ClosedItemFixture):
    """The closed-item "not checked" systemMessage rides on a block for another reason, so the owner sees that the
    check did not run. The block here is the Departs-from check of a pick with no Departs from line. The copy is
    unreadable and item 381 is cited, so the closed-item check has a note and no refusal."""

    PICK = "Two ways for item 381:\n> A (my pick): fold the guard\n> B: add a second hook"

    def assert_blocked_with_note(self, out, what):
        self.assertIsNotNone(out, "%s: no block and no note" % what)
        self.assertEqual(out.get("decision"), "block", "%s: no block: %r" % (what, out))
        self.assertIn("Departs-from guard", out.get("reason", ""),
                      "%s: the block is not the Departs-from check: %r" % (what, out))
        self.assertIn("not checked", out.get("systemMessage", ""),
                      "%s: the block carries no not-checked systemMessage: %r" % (what, out))

    def test_unlanded_block_carries_the_not_checked_note(self):
        # Catches: the closed-item note dropped from an unlanded turn's block (the block_note spread on that path).
        repo = copy_repo("torn-ref", CLOSED_214, torn=True)
        out = self.stop(self.turn(report(self.PICK)), repo)
        self.assert_blocked_with_note(out, "an unlanded turn, a pick with no Departs from line, item 381 cited")

    def test_landed_block_carries_the_not_checked_note(self):
        # Catches: the closed-item note dropped from a landed turn's block (the block_note spread on that path).
        repo = copy_repo("torn-ref", CLOSED_214, torn=True)
        commit = [trg.tool_use_msg("Bash", {"command": COMMIT}, id_="g1"),
                  trg.tool_result_msg("g1", "[main abc123] step")]
        out = self.stop(self.turn(report(self.PICK), *commit), repo)
        self.assert_blocked_with_note(out, "a landed turn, a pick with no Departs from line, item 381 cited")


class ClosedItemCostTests(ClosedItemFixture):
    """The copy is read once per Stop: the reader's one git grep, however many items the report cites."""

    def test_three_cites_read_the_copy_once(self):
        # Catches: one git read of the copy per cited item.
        repo = copy_repo("closed-all", CLOSED_ALL)
        trace = os.path.join(self.run_dir, "three.trace")
        self.stop(self.turn(report("items 214, 381 and 383 are open.")), repo, trace=trace)
        self.assertEqual(copy_reads(trace), 1, "the copy was read %d times for three cites, not once" % copy_reads(trace))

    def test_a_stop_with_no_cite_reads_the_copy_at_most_once(self):
        # Catches: a copy read repeated for each line of a report that cites nothing.
        repo = copy_repo("closed-all", CLOSED_ALL)
        trace = os.path.join(self.run_dir, "none.trace")
        self.stop(self.turn(report("none.")), repo, trace=trace)
        self.assertLessEqual(copy_reads(trace), 1, "the copy was read %d times for a report with no cite" % copy_reads(trace))


class ClosedItemFailOpenTests(ClosedItemFixture):
    """Each one must pass the Stop with a systemMessage that says the check was not run."""

    def test_no_record_branch_passes_with_a_not_checked_note(self):
        # Catches: a missing record branch read as a closed item, or as no note at all.
        repo = tfi.shared_repo("no-record-branch", lambda: tfi.make_repo(
            "no-record-branch", tracked=("decisions/a-ruling.md",), extras=tfi.filing_extras()))
        out = self.stop(self.turn(report("item 214 is open.")), repo)
        self.assert_not_checked(out, "no record branch ref")

    def test_no_items_folder_passes_with_a_not_checked_note(self):
        # Catches: a record branch with no items folder read as a closed item, or as no note at all.
        repo = tfi.record_repo("no-items", {"waiting/notes.txt": "notes, no items folder\n"})
        out = self.stop(self.turn(report("item 214 is open.")), repo)
        self.assert_not_checked(out, "a record branch with no items folder")

    def test_bad_item_json_passes_with_a_not_checked_note(self):
        # Catches: an item file that is not a JSON object read as a closed item, or as no note at all.
        repo = tfi.record_repo("bad-json", {"waiting/items/n214.json": BAD_ITEM})
        out = self.stop(self.turn(report("item 214 is open.")), repo)
        self.assert_not_checked(out, "an item file that is not a JSON object")

    def test_git_error_passes_with_a_not_checked_note(self):
        # Catches: a git error read as a closed item, or as no note at all. The ref points at no object.
        repo = copy_repo("torn-ref", CLOSED_214, torn=True)
        out = self.stop(self.turn(report("item 214 is open.")), repo)
        self.assert_not_checked(out, "a record branch ref git cannot read")


if __name__ == "__main__":
    unittest.main()
