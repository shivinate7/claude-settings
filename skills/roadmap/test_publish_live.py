"""Fixture suite for publish_live.py. Run: python3 skills/roadmap/test_publish_live.py

Saves fixture reads in a folder, runs the publisher, then loads its file through build.live_work, the reader
the build uses.
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent.parent / "lint"))
import _test_temp  # noqa: E402  test-temp-standard (lint/_test_temp.py)
import build  # noqa: E402

RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def pull(number, ref, closed_at=None, merged=False, base="main"):
    row = {"number": number, "title": "t%d" % number, "draft": True, "created_at": "2026-11-12T00:00:00Z",
           "base": {"ref": base}, "head": {"ref": ref, "sha": "sha%d" % number}}
    if closed_at:
        row.update(closed_at=closed_at, merged_at="2026-11-13T00:00:00Z" if merged else None)
    return row


def sess(sid, status, updated, tags=None, bucket="SESSION_STATUS_BUCKET_WORKING"):
    row = {"id": sid, "title": "x", "session_status": status, "updated_at": updated, "status_bucket": bucket}
    if tags is not None:
        row["tags"] = tags
    return row


class PublishLive(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(dir=RUN_FOLDER))
        self.save("open_p1.json", [pull(7, "lane-x"), pull(9, "s2")])
        self.save("closed_p1.json", [pull(20, "old", "2026-10-01T00:00:00Z"), pull(21, "new", "2026-11-12T00:00:00Z", True),
                                     pull(22, "other-base", "2026-11-12T00:00:00Z", base="dev")])
        self.save("sess_p1.json", [sess("session_a", "SESSION_STATUS_IDLE", "2026-11-13T09:00:00Z", ["cs-repo:o/r", "cs-step:s1"]),
                                   sess("session_b", "SESSION_STATUS_RUNNING", "2026-11-13T09:30:00Z", ["cs-repo:o/r"])])
        self.save("sess_p2.json", [sess("session_c", "SESSION_STATUS_IDLE", "2026-11-13T08:00:00Z")])  # tags absent
        self.save("prev.json", {"landedPulls": [{"number": 5, "branch": "b5", "merged": True}],
                                "sessions": [{"id": "session_b", "unarchived_epoch": 1789000000}],
                                "keepSessions": [{"id": "session_a", "reason": "r"}]})
        (self.dir / "held.txt").write_text("# runner list\n9  # nine\n", encoding="utf-8")
        (self.dir / "readat.txt").write_text("2026-11-13T10:00:00Z\n", encoding="utf-8")
        (self.dir / "items" / "items").mkdir(parents=True)
        self.save("items/items/1.json", {"n": 1, "status": "open", "home": "h", "extra": "dropped"})
        self.save("items/items/2.json", {"data": {"n": 2, "status": "open", "home": "h", "lane": None}})

    def save(self, name, value):
        (self.dir / name).write_text(json.dumps(value), encoding="utf-8")

    def run_pub(self):
        return subprocess.run([sys.executable, "-I", str(HERE / "publish_live.py"), "--dir", str(self.dir),
                               "--landed-since", "2026-10-30T12:20:00Z"], capture_output=True, text=True)

    def published(self):
        done = self.run_pub()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return json.loads((self.dir / "live.json").read_text(encoding="utf-8"))

    def test_fields_and_build_reads_them(self):
        raw = self.published()
        by_id = {r["id"]: r for r in raw["sessions"]}
        self.assertEqual(by_id["session_a"]["idle_since"], "2026-11-13T09:00:00Z")
        self.assertEqual(by_id["session_c"]["idle_since"], "2026-11-13T08:00:00Z")
        self.assertEqual(by_id["session_c"]["tags"], [])
        self.assertNotIn("idle_since", by_id["session_b"])  # not idle
        self.assertEqual(by_id["session_b"]["unarchived_epoch"], 1789000000)
        self.assertNotIn("unarchived_epoch", by_id["session_a"])  # none in prev: absent
        self.assertEqual({p["number"]: p["held"] for p in raw["pulls"]}, {7: False, 9: True})
        self.assertNotIn("reviewLog", json.dumps(raw))
        self.assertEqual(sorted(r["number"] for r in raw["landedPulls"]), [5, 21])
        self.assertEqual([r["n"] for r in raw["items"]], [1, 2])
        self.assertEqual(raw["items"][0], {"n": 1, "status": "open", "home": "h"})
        live = build.live_work(str(self.dir / "live.json"), {}, "o/r")
        self.assertEqual((live["read"], live["skipped"]), ("2026-11-13T10:00:00Z", []))
        self.assertEqual({p["number"]: p["held"] for p in live["pulls"]}, {7: False, 9: True})
        self.assertEqual([r["id"] for r in live["laneSessions"]], ["session_a", "session_b", "session_c"])
        self.assertEqual(sorted(r["number"] for r in live["landedPulls"]), [5, 21])

    def test_all_line_holds_every_pull(self):
        (self.dir / "held.txt").write_text("ALL\n", encoding="utf-8")
        self.assertTrue(all(p["held"] for p in self.published()["pulls"]))

    def test_gapped_or_missing_reads_stop_and_write_nothing(self):
        self.save("sess_p4.json", [])  # page 3 missing
        done = self.run_pub()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("pages missing: 3", done.stderr)
        self.assertFalse((self.dir / "live.json").exists())
        (self.dir / "sess_p4.json").unlink()
        (self.dir / "open_p1.json").unlink()
        self.assertNotEqual(self.run_pub().returncode, 0)
        self.assertFalse((self.dir / "live.json").exists())


if __name__ == "__main__":
    unittest.main()
