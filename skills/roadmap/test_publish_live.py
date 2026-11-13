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
                                "sessions": [{"id": "session_b", "unarchived_epoch": 1789000000}, {"id": "session_a"}],
                                "keepSessions": [{"id": "session_a", "reason": "r"}]})
        (self.dir / "held.txt").write_text("# runner list\n9  # nine\n", encoding="utf-8")
        (self.dir / "readat.txt").write_text("2026-11-13T10:00:00Z\n", encoding="utf-8")
        self.save("pages.json", {"open": 1, "closed": 1, "sess": 2})
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
        landed = {r["number"]: r for r in raw["landedPulls"]}
        self.assertEqual(landed[21]["closed_at"], "2026-11-12T00:00:00Z")
        self.assertEqual(landed[5]["closed_at"], "2026-11-13T10:00:00Z")  # a prev row with none is stamped with this read
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

    def stops(self, message):
        done = self.run_pub()
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn(message, done.stderr)
        self.assertFalse((self.dir / "live.json").exists())

    def test_missing_items_folder_omits_the_key(self):
        for path in sorted((self.dir / "items").glob("**/*.json")):
            path.unlink()
        (self.dir / "items" / "items").rmdir()
        (self.dir / "items").rmdir()
        raw = self.published()
        self.assertNotIn("items", raw)
        self.assertTrue(build.live_work(str(self.dir / "live.json"), {}, "o/r")["itemsWhy"].startswith("unknown"))

    def test_hold_lines(self):
        (self.dir / "held.txt").write_text("#9\n# comment\n7 # seven\n", encoding="utf-8")
        self.assertEqual({p["number"]: p["held"] for p in self.published()["pulls"]}, {7: True, 9: True})
        (self.dir / "live.json").unlink()
        for bad in ("all\n", "PR 9\n", "9 7\n"):
            (self.dir / "held.txt").write_text(bad, encoding="utf-8")
            self.stops("held.txt line")

    def test_wrong_types_stop(self):
        prev = json.loads((self.dir / "prev.json").read_text(encoding="utf-8"))
        for bad in (1.0, "0", True):
            prev["sessions"] = [{"id": "session_b", "unarchived_epoch": bad}]
            self.save("prev.json", prev)
            self.stops("unarchived_epoch")
        self.save("prev.json", {"landedPulls": [], "keepSessions": []})
        self.save("sess_p2.json", [sess("session_c", "SESSION_STATUS_IDLE", "2026-11-13T08:00:00")])  # no zone
        self.stops("idle_since")
        self.save("sess_p2.json", [sess("session_c", "SESSION_STATUS_IDLE", "2026-11-13T08:00:00Z")])
        self.save("items/items/1.json", {"n": "1", "status": "open", "home": "h"})
        self.stops("item")
        self.save("items/items/1.json", {"n": 1, "status": "open", "home": "h"})
        self.save("open_p1.json", [dict(pull(7, "lane-x"), number="7")])
        self.stops("number")

    def test_a_lost_last_page_stops(self):
        self.save("pages.json", {"open": 1, "closed": 1, "sess": 3})  # triage read 3 session pages; 2 are saved
        self.stops("sess pages missing: 3")
        self.save("pages.json", {"open": 1, "closed": 1, "sess": 1})  # more files than were read
        self.stops("sess")
        (self.dir / "pages.json").unlink()
        self.stops("pages.json")

    def test_hash_all_is_not_a_comment(self):
        (self.dir / "held.txt").write_text("#ALL\n", encoding="utf-8")
        self.stops("held.txt line")

    def test_landed_rows_expire_after_14_days(self):
        self.save("prev.json", {"landedPulls": [
            {"number": 5, "branch": "b5", "merged": True, "closed_at": "2026-10-30T10:00:00Z"},
            {"number": 6, "branch": "b6", "merged": True, "closed_at": "2026-10-30T10:00:01Z"}]})
        raw = self.published()  # readAt 2026-11-13T10:00:00Z: the cut is 2026-10-30T10:00:00Z
        self.assertEqual(sorted(r["number"] for r in raw["landedPulls"]), [5, 6, 21])
        self.save("prev.json", {"landedPulls": [{"number": 5, "branch": "b5", "closed_at": "2026-10-30T09:59:59Z"}]})
        self.assertEqual(sorted(r["number"] for r in self.published()["landedPulls"]), [21])

    def test_landed_window_compares_instants(self):
        self.save("closed_p1.json", [pull(21, "a", "2026-11-06T13:00:00Z", True)])
        done = subprocess.run([sys.executable, "-I", str(HERE / "publish_live.py"), "--dir", str(self.dir),
                               "--landed-since", "2026-11-06T12:00:00-06:00"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)  # 13:00Z is before 18:00Z: outside the window
        landed = json.loads((self.dir / "live.json").read_text(encoding="utf-8"))["landedPulls"]
        self.assertEqual([r["number"] for r in landed], [5])

    def test_gapped_or_missing_reads_stop_and_write_nothing(self):
        self.save("pages.json", {"open": 1, "closed": 1, "sess": 4})
        self.save("sess_p4.json", [])  # page 3 missing
        done = self.run_pub()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("pages missing: 3", done.stderr)
        self.assertFalse((self.dir / "live.json").exists())
        (self.dir / "sess_p4.json").unlink()
        self.save("pages.json", {"open": 1, "closed": 1, "sess": 2})
        (self.dir / "open_p1.json").unlink()
        self.assertNotEqual(self.run_pub().returncode, 0)
        self.assertFalse((self.dir / "live.json").exists())


if __name__ == "__main__":
    unittest.main()
