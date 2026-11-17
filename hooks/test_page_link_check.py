#!/usr/bin/env python3
"""Cases for the Stop check that makes the page writer print the waiting page's link in its last reply of
the turn (roadmap step surface-page-link-in-chat; skill waiting-page, section "Print the page link").
Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_page_link_check.py

The fixtures and the Stop runner are those of hooks/test_waiting_export.py, imported here, not copied. Each
case runs hooks/feedback_guard.py as the Stop hook does, with the transcript it names. The copy commit comes
after the 19:00 write, so the export check passes in every case and only the link check can block.

Each block case is P01 with one change, and each pass case is G01 with one change, so each result is caused
by that change. P01 is the canonical red: a stub that always passes fails it.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_waiting_export as twe  # noqa: E402  the shared fixtures and run_stop (one home)
from shared_names import MACHINE_TAGS, TASK_NOTIFICATION_TAG  # noqa: E402  the machine notice tags, one home
import layout  # noqa: E402  the registry and the waiting page id (lint/layout.py)

LINK = "https://claude.ai/artifact/"  # the link form the reason names
CODE_URL = "https://claude.ai/code/artifact/" + twe.PAGE_ID  # the same artifact, the other URL form
WAIT2_URL = "https://claude.ai/artifact/" + twe.PAGE_ID + "2"  # an id that only starts with the page id
MISSING = os.path.join(twe.ROOT, "missing", "transcript.jsonl")  # a transcript path with no file
FROZEN_NAMES = ("feedback_guard", "settings.json")  # the frozen hook and settings files (hooks/guard_frozen.py)


# --------------------------------------------------------------------------- fixtures

def page_of(root):
    """The repo's waiting page URL, read through layout."""
    return layout.waiting_page(root)  # glossary-ok: layout's function name, a code name the glossary keeps


def page_repo(name, extras=None):
    """A repo whose copy has a commit at 17:00 and one at 20:00, so the 19:00 write is covered by the export."""
    root = twe.roadmap_repo(name, [(twe.at(17), twe.item(twe.FOLDER, 1)), (twe.at(20), twe.item(twe.FOLDER, 2))],
                            extras=extras)
    twe.check("%s scope: the newest copy commit is after the 19:00 write" % name.upper(),
              twe.newest_copy(root, twe.FOLDER) == twe.at(20), twe.newest_copy(root, twe.FOLDER))
    return root


def queue_repo(name):
    """A repo whose waiting page is QUEUE_ID, so a link to PAGE_URL names another artifact."""
    root = page_repo(name, extras=twe.registry(page_id=twe.QUEUE_ID, page_url=twe.QUEUE_URL))
    twe.check("%s scope: the waiting page id is %s" % (name.upper(), twe.QUEUE_ID),
              layout.artifact_id(page_of(root)) == twe.QUEUE_ID, page_of(root))
    return root


def no_page_repo(name):
    """A repo with a reference artifact and no waiting page."""
    data = json.loads(twe.registry())
    data["artifacts"] = [a for a in data["artifacts"] if a["role"] != "waiting-page"]
    root = twe.make_repo(name, json.dumps(data))
    twe.check("%s scope: the repo names no waiting page" % name.upper(), page_of(root) == "unknown",
              page_of(root))
    return root


def page_turn(reply, when=19, **write):
    """One turn: the owner's message, a page write at `when`:00, and one reply text. `write` goes to page_write."""
    return [twe.owner(twe.at(18, 50))] + twe.page_write(twe.at(when), **write) + [twe.say(twe.at(when, 2), reply)]


# --------------------------------------------------------------------------- expectations

def expect_link_block(name, p):
    """A block whose reason names the link form, and names no frozen hook or settings file."""
    obj = twe.expect_block(name, p, (LINK,))
    reason = obj.get("reason") or ""
    twe.check(name + ": the reason names no frozen hook or settings file",
              not any(word in reason for word in FROZEN_NAMES), reason)


# --------------------------------------------------------------------------- block cases (red on the old code)

def case_p01_writes_page_reply_lacks_id_blocks():
    """The canonical red: the writer posts an item and its last reply names no link."""
    expect_link_block("P01", twe.run_stop("p01", page_repo("p01"), page_turn("Done.")))


def case_p02_update_of_the_page_blocks():
    """P01 with one change: the write is an update."""
    expect_link_block("P02", twe.run_stop("p02", page_repo("p02"), page_turn("Done.", action="update")))


def case_p03_batch_write_blocks():
    """P01 with one change: the write is a batch that names an exported collection."""
    expect_link_block("P03", twe.run_stop("p03", page_repo("p03"), page_turn("Done.", action="batch")))


def case_p04_delete_of_an_exported_collection_blocks():
    """P01 with one change: the write deletes an answer, and answers is exported."""
    records = [twe.owner(twe.at(18, 50))] + twe.page_write(twe.at(19), action="delete", collection=None,
                                                          doc_id="answers/a1") + [twe.say(twe.at(19, 2), "Done.")]
    expect_link_block("P04", twe.run_stop("p04", page_repo("p04"), records))


def case_p05_link_only_in_an_earlier_text_blocks():
    """P01 with one change: the link is in an earlier text of the turn, and the last text names none."""
    records = [twe.owner(twe.at(18, 50))] + twe.page_write(twe.at(19)) + [
        twe.say(twe.at(19, 2), "Link: " + twe.PAGE_URL),
        twe.call(twe.at(19, 3), "b2", "Bash", {"command": "ls"}), twe.result(twe.at(19, 4), "b2", "README.md\n"),
        twe.say(twe.at(19, 5), "Done.")]
    expect_link_block("P05", twe.run_stop("p05", page_repo("p05"), records))


def case_p06_link_only_in_the_previous_turn_blocks():
    """P01 with one change: the link is in the reply of an earlier turn, and this turn's reply names none."""
    records = [twe.owner(twe.at(18, 40), "first turn"), twe.say(twe.at(18, 41), "Link: " + twe.PAGE_URL),
               twe.owner(twe.at(18, 50), "second turn")] + twe.page_write(twe.at(19)) + [
        twe.say(twe.at(19, 2), "Done.")]
    expect_link_block("P06", twe.run_stop("p06", page_repo("p06"), records))


def case_p07_machine_notice_does_not_start_a_turn_blocks():
    """P01 with one change: a system notice comes after the write. It is no real user message, so the write
    stays in the turn and the last reply still has to name the link."""
    records = page_turn("Done.") + [twe.rec(twe.at(19, 3), "user", MACHINE_TAGS[0] + "\nA notice.\n"),
                                    twe.say(twe.at(19, 4), "All set.")]
    expect_link_block("P07", twe.run_stop("p07", page_repo("p07"), records))


def case_p08_reply_links_another_artifact_blocks():
    """P01 with one change: the reply links the reference artifact, not the waiting page."""
    expect_link_block("P08", twe.run_stop("p08", page_repo("p08"), page_turn("Link: " + twe.REF_URL)))


def case_p09_reply_links_an_id_that_only_starts_with_the_page_id_blocks():
    """P01 with one change: the reply links an id that begins with the page id. The id compares whole."""
    expect_link_block("P09", twe.run_stop("p09", page_repo("p09"), page_turn("Link: " + WAIT2_URL)))


def case_p10_queue_page_reply_with_the_old_id_blocks():
    """The waiting page is QUEUE_ID, and the reply links the old page id. The id is read from layout, not fixed."""
    root = queue_repo("p10")
    expect_link_block("P10", twe.run_stop("p10", root, page_turn("Link: " + twe.PAGE_URL, url=twe.QUEUE_URL)))


def case_p11_full_size_turn_with_no_link_blocks():
    """P01 at full size: a turn of many texts, none of which names the link."""
    records = [twe.owner(twe.at(18, 50))] + twe.page_write(twe.at(19)) + [
        twe.say(twe.at(19, 2), "filler %d" % k) for k in range(twe.FULL_SIZE)]
    twe.check("P11 scope: the turn holds %d or more records" % twe.FULL_SIZE, len(records) > twe.FULL_SIZE,
              len(records))
    expect_link_block("P11", twe.run_stop("p11", page_repo("p11"), records))


# --------------------------------------------------------------------------- pass cases (green on the old code)

def case_g01_reply_with_the_link_passes():
    """P01 with one change: the reply names the page's link."""
    twe.expect_pass("G01", twe.run_stop("g01", page_repo("g01"), page_turn("Page: " + twe.PAGE_URL)))


def case_g02_code_form_link_passes():
    """G01 with the /code/artifact/ form of the same link: layout.artifact_id compares the id."""
    twe.expect_pass("G02", twe.run_stop("g02", page_repo("g02"), page_turn("Page: " + CODE_URL)))


def case_g03_queue_page_reply_with_its_own_link_passes():
    """The queue page, and the reply names its link."""
    root = queue_repo("g03")
    twe.expect_pass("G03", twe.run_stop("g03", root, page_turn("Page: " + twe.QUEUE_URL, url=twe.QUEUE_URL)))


def case_g04_read_only_turn_passes():
    """P01 with one change: the page is read, not written."""
    twe.expect_pass("G04", twe.run_stop("g04", page_repo("g04"), page_turn("Done.", action="get")))


def case_g05_write_in_an_earlier_turn_passes():
    """The write is in an earlier turn. The check reads this turn only, so the earlier write does not count."""
    records = ([twe.owner(twe.at(18, 40), "first turn")] + twe.page_write(twe.at(18, 45))
               + [twe.say(twe.at(18, 46), "Done.")]
               + [twe.owner(twe.at(19, 30), "second turn"), twe.say(twe.at(19, 31), "Done.")])
    twe.expect_pass("G05", twe.run_stop("g05", page_repo("g05"), records))


def case_g06_errored_write_passes():
    """P01 with one change: the write's result is an error, so nothing was written."""
    twe.expect_pass("G06", twe.run_stop("g06", page_repo("g06"), page_turn("Done.", is_error=True)))


def case_g07_write_to_another_artifact_passes():
    """P01 with one change: the write goes to the reference artifact."""
    twe.expect_pass("G07", twe.run_stop("g07", page_repo("g07"), page_turn("Done.", url=twe.REF_URL)))


def case_g08_write_to_an_unexported_collection_passes():
    """P01 with one change: the write sets scratch/x, which no export list names, so the page does not export it."""
    records = [twe.owner(twe.at(18, 50))] + twe.page_write(twe.at(19), collection=None, doc_id="scratch/x") + [
        twe.say(twe.at(19, 2), "Done.")]
    twe.expect_pass("G08", twe.run_stop("g08", page_repo("g08"), records))


def case_g09_repo_without_a_page_passes():
    """P01 in a repo with no waiting page: there is no link to print."""
    twe.expect_pass("G09", twe.run_stop("g09", no_page_repo("g09"), page_turn("Done.")))


def case_g10_another_session_is_the_writer_passes():
    """P01 with one change: the transcript names another session as the page writer."""
    twe.expect_pass("G10", twe.run_stop("g10", page_repo("g10"), page_turn("Done."), writer="session_other"))


def case_g11_empty_transcript_passes():
    """The empty state: a transcript file with no records."""
    twe.expect_pass("G11", twe.run_stop("g11", page_repo("g11"), None))


def case_g12_unreadable_transcript_passes():
    """The transcript path names no file. The check fails open, as export_check does."""
    twe.check("G12 scope: the transcript path names no file", not os.path.exists(MISSING), MISSING)
    twe.expect_pass("G12", twe.run_stop("g12", page_repo("g12"), None, transcript_path=MISSING))


def case_g13_full_size_turn_that_ends_with_the_link_passes():
    """P11 with one change: the last text of the full-size turn names the link."""
    records = [twe.owner(twe.at(18, 50))] + twe.page_write(twe.at(19)) + [
        twe.say(twe.at(19, 2), "filler %d" % k) for k in range(twe.FULL_SIZE)] + [
        twe.say(twe.at(19, 3), "Page: " + twe.PAGE_URL)]
    twe.expect_pass("G13", twe.run_stop("g13", page_repo("g13"), records))


# --------------------------------------------------------------------------- later wakes (A) and meta stamps (B)

def wake_records():
    """Three wakes after a reply: a task notification, a system reminder and a framed cross-session peer message.
    None starts a turn, and none is the owner's message."""
    peer = twe.rec(twe.at(19, 5), "user", "<cross-session-message>\nLane merged.\n</cross-session-message>")
    peer["origin"] = {"kind": "peer", "fromSession": "session_lane"}
    return [twe.rec(twe.at(19, 3), "user", TASK_NOTIFICATION_TAG + "\nLane done.\n"),
            twe.rec(twe.at(19, 4), "user", MACHINE_TAGS[0] + "\nA reminder.\n"), peer]


def case_a01_write_covered_by_a_linked_reply_passes_after_a_wake():
    """The write's reply named the link before three wakes, and the last reply after them names none. The write is
    covered by the linked reply, so no link is owed again."""
    records = page_turn("Link: " + twe.PAGE_URL) + wake_records() + [twe.say(twe.at(19, 6), "Lane merged.")]
    twe.expect_pass("A01", twe.run_stop("a01", page_repo("a01"), records))


def case_a02_write_after_a_covered_wake_still_blocks():
    """A01 with one change: the turn posts an item after the wake. That write is owed its own link."""
    records = (page_turn("Link: " + twe.PAGE_URL) + wake_records()
               + twe.page_write(twe.at(19, 6), tid="w2", doc_id="fb-2") + [twe.say(twe.at(19, 8), "Lane merged.")])
    expect_link_block("A02", twe.run_stop("a02", page_repo("a02"), records))


def case_b01_meta_page_update_with_nothing_to_do_passes():
    """A turn whose only page write stamps meta/page. The stamp is no item, so no link is owed."""
    records = ([twe.owner(twe.at(18, 50))]
               + twe.page_write(twe.at(19), action="update", collection=None, doc_id=None, path="meta/page")
               + [twe.say(twe.at(19, 2), "Nothing to do.")])
    twe.expect_pass("B01", twe.run_stop("b01", page_repo("b01"), records))


def case_b02_meta_stamp_with_an_item_write_still_blocks():
    """B01 with one change: an item is posted in the same turn, so that write is owed its link."""
    records = ([twe.owner(twe.at(18, 50))]
               + twe.page_write(twe.at(19), action="update", collection=None, doc_id=None, path="meta/page")
               + twe.page_write(twe.at(19, 2), tid="w2", doc_id="fb-2")
               + [twe.say(twe.at(19, 4), "Nothing to do.")])
    expect_link_block("B02", twe.run_stop("b02", page_repo("b02"), records))


def case_b03_groups_and_asks_writes_still_block():
    """Posting to the other exported collections is still a write that owes the link: groups and asks."""
    for collection in ("groups", "asks"):
        label = "b03-" + collection
        expect_link_block("B03 %s" % collection,
                          twe.run_stop(label, page_repo(label), page_turn("Nothing to do.", collection=collection,
                                                                          doc_id="x1")))


def case_b04_receipts_write_blocks():
    """B03 with one change: the write is a receipt, `receipts/x`. Receipts are exported, so they owe the link."""
    expect_link_block("B04", twe.run_stop("b04", page_repo("b04"), page_turn("Nothing to do.", collection=None,
                                                                            doc_id="receipts/x")))


def case_b05_receipts_write_with_the_link_passes():
    """B04 with one change: the reply names the page's link."""
    twe.expect_pass("B05", twe.run_stop("b05", page_repo("b05"), page_turn("Page: " + twe.PAGE_URL, collection=None,
                                                                          doc_id="receipts/x")))


CASES = (
    case_p01_writes_page_reply_lacks_id_blocks,
    case_p02_update_of_the_page_blocks,
    case_p03_batch_write_blocks,
    case_p04_delete_of_an_exported_collection_blocks,
    case_p05_link_only_in_an_earlier_text_blocks,
    case_p06_link_only_in_the_previous_turn_blocks,
    case_p07_machine_notice_does_not_start_a_turn_blocks,
    case_p08_reply_links_another_artifact_blocks,
    case_p09_reply_links_an_id_that_only_starts_with_the_page_id_blocks,
    case_p10_queue_page_reply_with_the_old_id_blocks,
    case_p11_full_size_turn_with_no_link_blocks,
    case_g01_reply_with_the_link_passes,
    case_g02_code_form_link_passes,
    case_g03_queue_page_reply_with_its_own_link_passes,
    case_g04_read_only_turn_passes,
    case_g05_write_in_an_earlier_turn_passes,
    case_g06_errored_write_passes,
    case_g07_write_to_another_artifact_passes,
    case_g08_write_to_an_unexported_collection_passes,
    case_g09_repo_without_a_page_passes,
    case_g10_another_session_is_the_writer_passes,
    case_g11_empty_transcript_passes,
    case_g12_unreadable_transcript_passes,
    case_g13_full_size_turn_that_ends_with_the_link_passes,
    case_a01_write_covered_by_a_linked_reply_passes_after_a_wake,
    case_a02_write_after_a_covered_wake_still_blocks,
    case_b01_meta_page_update_with_nothing_to_do_passes,
    case_b02_meta_stamp_with_an_item_write_still_blocks,
    case_b03_groups_and_asks_writes_still_block,
    case_b04_receipts_write_blocks,
    case_b05_receipts_write_with_the_link_passes,
)


def main():
    try:
        for case in CASES:
            twe.run_case(case)
    finally:
        shutil.rmtree(twe.ROOT, ignore_errors=True)
    if twe.RED_CASES:
        print("test_page_link_check FAIL: %d of %d cases red" % (len(twe.RED_CASES), len(CASES)))
        print("red: " + ", ".join(twe.RED_CASES))
        return 1
    print("test_page_link_check PASS: all %d cases green" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
