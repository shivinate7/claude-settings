#!/usr/bin/env python3
"""Cases for lint/_transcript.py's page-writer reads: `page_read_ran` and `page_writer_id`, both read by _page_reads.

A Mac claude-artifacts db_get of meta/page is the same read as an ArtifactData get of it. _page_reads reads each call
through data_call, the one mapping (hooks/shared_names.py canonical_artifact_call), so the Mac read counts as the page
read. The controls: a Mac get of another document, a Mac write, and a read in a sidechain count as nothing.
Standard library only, and no test runner.

Run it from the repository root:

    python3 lint/test_transcript.py
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _transcript  # noqa: E402  the one home of the transcript reads

MAC_DB_GET = "mcp__claude-artifacts__db_get"
MAC_DB_WRITE = "mcp__claude-artifacts__db_write"
WRITER = "session_writer7"


def call_rec(name, tool_input, tool_id, sidechain=False):
    """An assistant record holding one tool_use: its name, its input and its id."""
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"content": [{"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}}


def result_rec(tool_id, content):
    """A user record holding the tool_result of `tool_id`."""
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id,
                                                     "content": content}]}}


def page_get(tool_id, name=MAC_DB_GET, path="meta/page"):
    """A Mac db call that reads `path`, and the result that names the writer."""
    return [call_rec(name, {"url": "https://claude.ai/artifact/waitpage", "path": path}, tool_id),
            result_rec(tool_id, json.dumps({"writer": WRITER}))]


class PageReadsOfMacCalls(unittest.TestCase):
    def test_mac_db_get_of_meta_page_is_a_page_read(self):
        # Catches: a Mac db_get of meta/page not read as the ArtifactData get of it, so the writer is never named.
        records = page_get("m1")
        self.assertTrue(_transcript.page_read_ran(records), "a Mac db_get of meta/page is not a page read")
        self.assertEqual(_transcript.page_writer_id(records), WRITER,
                         "a Mac db_get of meta/page does not name the page writer")

    def test_mac_db_get_of_meta_page_with_no_writer_still_counts_as_a_read(self):
        # Catches: the read depending on its result. A read that names no writer is still a read the page ran.
        records = [call_rec(MAC_DB_GET, {"path": "meta/page"}, "m2"), result_rec("m2", "{}")]
        self.assertTrue(_transcript.page_read_ran(records), "a Mac db_get of meta/page with no writer is not a page read")
        self.assertIsNone(_transcript.page_writer_id(records))

    def test_mac_db_get_of_another_document_is_no_page_read(self):
        # Catches: any Mac db_get counted as the page read, whatever it reads.
        records = page_get("m3", path="answers/a-7k2")
        self.assertFalse(_transcript.page_read_ran(records), "a Mac db_get of answers counts as a page read")
        self.assertIsNone(_transcript.page_writer_id(records))

    def test_mac_db_write_of_meta_page_is_no_page_read(self):
        # Catches: a write of meta/page counted as the read. Only a get reads the page writer.
        records = [call_rec(MAC_DB_WRITE, {"url": "https://claude.ai/artifact/waitpage",
                                           "ops": [{"op": "set", "path": "meta/page", "data": {"writer": WRITER}}]},
                            "m4")]
        self.assertFalse(_transcript.page_read_ran(records), "a Mac db_write of meta/page counts as a page read")

    def test_mac_db_get_in_a_sidechain_is_no_page_read(self):
        # Catches: a sidechain read taken for the main session's page read.
        records = [call_rec(MAC_DB_GET, {"path": "meta/page"}, "m5", sidechain=True),
                   result_rec("m5", json.dumps({"writer": WRITER}))]
        self.assertFalse(_transcript.page_read_ran(records), "a sidechain Mac db_get counts as a page read")


if __name__ == "__main__":
    unittest.main()
