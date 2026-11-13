"""Fixture suite for publish_live.py. Run: python3 skills/roadmap/test_publish_live.py

Feeds list_sessions rows, the open pulls and the batch runner's held list through the publisher, then loads
the file it wrote through build.live_work, the reader the build uses.
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

SLUG = "o/r"
SESSIONS = [
    {"id": "session_a", "session_status": "SESSION_STATUS_IDLE", "updated_at": "2026-11-13T09:00:00Z",
     "status_bucket": "SESSION_STATUS_BUCKET_REVIEW_READY", "tags": ["cs-repo:o/r", "cs-step:s1"], "title": "drop me"},
    {"id": "session_b", "session_status": "SESSION_STATUS_RUNNING", "updated_at": "2026-11-13T09:30:00Z",
     "tags": ["cs-repo:o/r", "cs-step:s2"], "unarchived_epoch": 1789000000},
    {"id": "session_c", "session_status": "SESSION_STATUS_IDLE", "updated_at": "2026-11-13T08:00:00Z"},
]
PULLS = [{"number": 7, "title": "seven", "branch": "lane-x", "draft": True},
         {"number": 9, "title": "nine", "branch": "s2", "draft": True, "head": "abc"}]
RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


class PublishLive(unittest.TestCase):
    def publish(self, held, sessions=SESSIONS, pulls=PULLS):
        tmp = pathlib.Path(tempfile.mkdtemp(dir=RUN_FOLDER))
        for name, value in (("sessions", sessions), ("pulls", pulls), ("held", held)):
            (tmp / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
        out = tmp / "live.json"
        done = subprocess.run([sys.executable, "-I", str(HERE / "publish_live.py"),
                               "--sessions", str(tmp / "sessions.json"), "--pulls", str(tmp / "pulls.json"),
                               "--held", str(tmp / "held.json"), "--read-at", "2026-11-13T10:00:00Z",
                               "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return json.loads(out.read_text(encoding="utf-8")), out

    def test_fields_written_and_read_by_build(self):
        raw, path = self.publish(held=[9, "#4"])
        by_id = {r["id"]: r for r in raw["sessions"]}
        self.assertEqual(by_id["session_a"]["idle_since"], "2026-11-13T09:00:00Z")
        self.assertEqual(by_id["session_c"]["idle_since"], "2026-11-13T08:00:00Z")
        self.assertNotIn("idle_since", by_id["session_b"])  # not idle
        self.assertEqual(by_id["session_b"]["unarchived_epoch"], 1789000000)
        self.assertNotIn("unarchived_epoch", by_id["session_a"])  # missing stays absent
        self.assertNotIn("title", by_id["session_a"])  # only the listed fields are copied
        self.assertEqual({p["number"]: p["held"] for p in raw["pulls"]}, {7: False, 9: True})
        self.assertNotIn("reviewLog", json.dumps(raw))  # part 2 of the step
        live = build.live_work(str(path), {}, SLUG)
        self.assertEqual(live["read"], "2026-11-13T10:00:00Z")
        self.assertEqual(live["skipped"], [])
        self.assertEqual({p["number"]: p["held"] for p in live["pulls"]}, {7: False, 9: True})
        self.assertEqual([r["id"] for r in live["laneSessions"]], ["session_a", "session_b", "session_c"])

    def test_wrong_shape_input_fails(self):
        tmp = pathlib.Path(tempfile.mkdtemp(dir=RUN_FOLDER))
        (tmp / "s.json").write_text("{}", encoding="utf-8")
        done = subprocess.run([sys.executable, "-I", str(HERE / "publish_live.py"), "--sessions", str(tmp / "s.json"),
                               "--pulls", str(tmp / "s.json"), "--held", str(tmp / "s.json"),
                               "--out", str(tmp / "o.json")], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertFalse((tmp / "o.json").exists())


if __name__ == "__main__":
    unittest.main()
