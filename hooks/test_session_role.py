#!/usr/bin/env python3
"""Cases for hooks/session_role.py, the one home of a local session's role file (lane local-tier-file). Stdlib and unittest.

    python3 hooks/test_session_role.py

Every case runs against a config directory of its own under the run folder (CLAUDE_CONFIG_DIR), so the live ~/.claude is never read.
The reader fails closed: each id, file or role that does not prove a role gives None. A refused os.replace writes no role and
leaves no temporary file. The folder is a pathlib path under the config directory.
"""
import json
import os
import io
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import session_role  # noqa: E402  the one home of the role file (hooks/session_role.py)
import guard_merge  # noqa: E402  the guard's local roadmap proof, read from the role file (hooks/guard_merge.py)

RUN_FOLDER = _test_temp.run_folder()
SID = "session-role-cases"  # passes the id shape: 8 to 200 characters of A-Za-z0-9._-
OTHER = "session-role-other"


class SessionRoleCase(unittest.TestCase):
    def setUp(self):
        self.cfg = tempfile.mkdtemp(prefix="session_role_cases_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.cfg, True)
        patch = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.cfg})
        patch.start()
        self.addCleanup(patch.stop)

    def folder(self):
        return os.path.join(self.cfg, "state", "session-roles")

    def put_file(self, name, text):
        os.makedirs(self.folder(), exist_ok=True)
        with open(os.path.join(self.folder(), name), "w", encoding="utf-8") as handle:
            handle.write(text)

    def put_role(self, name, session, role, repo="o/r"):
        self.put_file(name, json.dumps({"session": session, "role": role, "repo": repo}))


class OwnRoleIsNoneUnlessTheOwnFileProvesIt(SessionRoleCase):
    def test_no_id_gives_no_role_even_with_a_valid_file_present(self):
        self.put_role(SID + ".json", SID, "triage")
        for sid in (None, ""):
            with self.subTest(sid=sid):
                self.assertIsNone(session_role.own_role(sid), "a session with no id read a role file")

    def test_a_bad_id_gives_no_role_even_with_a_file_of_that_name(self):
        self.put_role("ltbad.json", "ltbad", "triage")  # 5 characters: fails the id shape
        self.assertIsNone(session_role.own_role("ltbad"), "an id outside the id shape read a role file")

    def test_a_missing_file_gives_no_role(self):
        self.assertIsNone(session_role.own_role(SID), "a missing role file gave a role")

    def test_a_file_for_another_id_gives_no_role(self):
        self.put_role(SID + ".json", OTHER, "triage")
        self.assertIsNone(session_role.own_role(SID), "a file that names another session gave a role")

    def test_bad_json_gives_no_role(self):
        self.put_file(SID + ".json", '{"session": ')
        self.assertIsNone(session_role.own_role(SID), "a malformed role file gave a role")

    def test_a_role_outside_the_launcher_list_gives_no_role(self):
        for role in ("lane", "boss", "", None):
            with self.subTest(role=role):
                self.put_role(SID + ".json", SID, role)
                self.assertIsNone(session_role.own_role(SID), "a role of %r gave a role" % (role,))

    def test_a_valid_file_gives_its_role(self):
        # Control: green on the built code. Without it the cases above could pass on a reader that always answers None.
        self.put_role(SID + ".json", SID, "batch-runner")
        self.assertEqual(session_role.own_role(SID), "batch-runner")
        self.assertEqual(session_role.own_record(SID)["repo"], "o/r")


class WriteFailsClosed(SessionRoleCase):
    def test_a_refused_replace_writes_no_role_and_leaves_no_temporary_file(self):
        # A reader holding the file open makes os.replace raise PermissionError on Windows. Patched here, since root does not
        # meet a permission error from chmod.
        with mock.patch.object(session_role.os, "replace", side_effect=PermissionError("held open")):
            self.assertFalse(session_role.write(SID, "", "triage"), "a refused replace reported success")
        self.assertIsNone(session_role.own_role(SID), "a refused replace left a role the reader trusts")
        leftover = [name for name in os.listdir(self.folder()) if name.endswith(".tmp")] if os.path.isdir(self.folder()) else []
        self.assertEqual(leftover, [], "a refused replace left a temporary file")


class RoleFolderIsAPathUnderTheConfigDir(SessionRoleCase):
    def test_the_folder_is_a_pathlib_path_under_the_config_dir(self):
        folder = session_role.roles_dir()
        self.assertIsInstance(folder, pathlib.Path)
        self.assertEqual(folder, pathlib.Path(self.cfg) / "state" / "session-roles")

    def test_a_write_lands_under_the_config_dir(self):
        self.assertTrue(session_role.write(SID, "", "batch-runner"), "a write to the config dir reported failure")
        self.assertTrue((pathlib.Path(self.cfg) / "state" / "session-roles" / (SID + ".json")).is_file(),
                        "the role file is not under the config dir")
        self.assertEqual(session_role.own_role(SID), "batch-runner")


# A fixed clock for prune_stale: no case reads the real one. A file stamped 1 is older than any real now by years, and a file
# stamped in 2100 is never older than seven days, so the write path needs no clock either.
T0 = 1800000000
STALE_EPOCH = 1
FRESH_FUTURE = 4102444800


class LocalJudgement(SessionRoleCase):
    """local_judgement, rules (a) and (c) of a local confirm: an own file is judged, and CS_SESSION_ROLE must agree with it."""

    def judge(self, launcher):
        with mock.patch.dict(os.environ, {"CS_SESSION_ROLE": launcher}):
            return session_role.local_judgement(SID)

    def test_an_own_file_is_judged_and_its_record_is_the_proof(self):
        self.put_role(SID + ".json", SID, "triage")
        self.assertEqual(self.judge(""), (True, {"session": SID, "role": "triage", "repo": "o/r"}),
                         "an own file was not judged, or its record is not the proof")

    def test_no_own_file_and_no_launcher_role_is_not_judged(self):
        self.put_role(OTHER + ".json", OTHER, "triage")  # another session's lingering file
        self.assertEqual(self.judge(""), (False, None), "a session with no own file and no launcher role was judged")

    def test_no_own_file_with_a_launcher_role_is_judged_with_no_record(self):
        self.assertEqual(self.judge("batch-runner"), (True, None), "a launcher session with no own file was not refused")

    def test_an_own_file_that_differs_from_the_launcher_role_gives_no_record(self):
        self.put_role(SID + ".json", SID, "batch-runner")
        self.assertEqual(self.judge("coordinator"), (True, None), "an own file that differs from the launcher role kept its record")

    def test_an_own_file_that_agrees_with_the_launcher_role_keeps_its_record(self):
        self.put_role(SID + ".json", SID, "batch-runner")
        self.assertEqual(self.judge("batch-runner"), (True, {"session": SID, "role": "batch-runner", "repo": "o/r"}),
                         "an own file that agrees with the launcher role lost its record")


class PruneStale(SessionRoleCase):
    def stamp(self, name, mtime):
        self.put_file(name, "{}")
        os.utime(os.path.join(self.folder(), name), (mtime, mtime))

    def present(self):
        return sorted(os.listdir(self.folder()))

    def test_prune_removes_a_file_older_than_seven_days_at_the_time_given(self):
        self.stamp("session-role-stale.json", T0 - 8 * 86400)
        self.stamp("session-role-fresh.json", T0 - 3600)
        session_role.prune_stale(now=T0)
        self.assertEqual(self.present(), ["session-role-fresh.json"],
                         "prune_stale did not judge the age against the time it was given")

    def test_a_write_removes_a_stale_file_and_keeps_a_fresh_one_and_its_own(self):
        self.stamp("session-role-stale.json", STALE_EPOCH)
        self.stamp("session-role-fresh.json", FRESH_FUTURE)
        self.assertTrue(session_role.write(SID, "", "triage"))
        self.assertEqual(self.present(), sorted(["session-role-fresh.json", SID + ".json"]),
                         "a write did not prune the stale file, or removed a fresh one or its own")


class WriteRefusals(SessionRoleCase):
    def test_an_id_outside_the_shape_writes_nothing_and_reports_it(self):
        self.assertFalse(session_role.write("ltbad", "", "triage"), "a write for an id outside the shape reported success")
        self.assertFalse(os.path.exists(os.path.join(self.folder(), "ltbad.json")), "a write for an id outside the shape made a file")

    def test_a_role_outside_the_list_removes_the_own_file(self):
        self.put_role(SID + ".json", SID, "triage")
        self.assertTrue(session_role.write(SID, "", ""), "a write with no role reported failure")
        self.assertFalse(os.path.exists(os.path.join(self.folder(), SID + ".json")), "a write with no role kept the own file")


class MainFromTheHook(SessionRoleCase):
    def run_main(self, argv, payload, launcher):
        with mock.patch.dict(os.environ, {"CS_SESSION_ROLE": launcher}), mock.patch("sys.stdin", io.StringIO(payload)):
            return session_role.main(argv)

    def test_a_write_from_the_hook_records_the_launcher_role(self):
        rc = self.run_main(["session_role.py", "write"], json.dumps({"session_id": SID, "cwd": ""}), "triage")
        self.assertEqual(rc, 0, "the hook's write exited %r" % (rc,))
        self.assertEqual(session_role.own_role(SID), "triage", "the hook did not record the launcher role")

    def test_no_launcher_role_removes_the_own_file_from_the_hook(self):
        self.put_role(SID + ".json", SID, "triage")
        rc = self.run_main(["session_role.py", "write"], json.dumps({"session_id": SID, "cwd": ""}), "")
        self.assertEqual(rc, 0, "the hook's write exited %r" % (rc,))
        self.assertFalse(os.path.exists(os.path.join(self.folder(), SID + ".json")), "the hook kept the own file with no launcher role")

    def test_another_command_line_writes_nothing(self):
        rc = self.run_main(["session_role.py", "prune"], json.dumps({"session_id": SID, "cwd": ""}), "triage")
        self.assertEqual(rc, 0, "a command other than write exited %r" % (rc,))
        self.assertIsNone(session_role.own_role(SID), "a command other than write recorded a role")

    def test_a_malformed_payload_writes_nothing_and_exits_0(self):
        rc = self.run_main(["session_role.py", "write"], "{not json", "triage")
        self.assertEqual(rc, 0, "a malformed payload exited %r" % (rc,))
        self.assertIsNone(session_role.own_role(SID), "a malformed payload recorded a role")

    def test_a_payload_that_is_not_an_object_writes_nothing_and_exits_0(self):
        rc = self.run_main(["session_role.py", "write"], "[1, 2]", "triage")
        self.assertEqual(rc, 0, "a payload that is not an object exited %r" % (rc,))
        self.assertIsNone(session_role.own_role(SID), "a payload that is not an object recorded a role")


class LocalRoleProof(SessionRoleCase):
    """guard_merge._local_role_proves: a local roadmap push is proved by the own file's role AND its repo. A wrong role or repo refuses."""

    def proves(self, roles, repo):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": SID}):
            return guard_merge._local_role_proves(SID, roles, repo)

    def test_the_own_role_must_be_one_of_the_roles_asked_for(self):
        self.put_role(SID + ".json", SID, "triage")
        self.assertTrue(self.proves(("triage",), "o/r"), "a triage file did not prove a triage push")
        self.assertFalse(self.proves(("coordinator",), "o/r"), "a triage file proved a coordinator push")

    def test_the_repo_must_equal_the_repo_the_file_names(self):
        self.put_role(SID + ".json", SID, "triage", repo="x/y")
        self.assertFalse(self.proves(("triage",), "o/r"), "a file for another repo proved this repo")
        self.put_role(SID + ".json", SID, "triage", repo=None)
        self.assertFalse(self.proves(("triage",), "o/r"), "a file with no repo proved this repo")
        self.put_role(SID + ".json", SID, "triage")
        self.assertFalse(self.proves(("triage",), None), "a push with no target repo was proved")

    def test_a_reader_that_cannot_run_refuses_with_false(self):
        # Injected fault: the reader raises, so the proof is refused with False, not with None, which a caller reads the same way.
        self.put_role(SID + ".json", SID, "triage")
        with mock.patch.object(session_role, "own_record", side_effect=RuntimeError("injected")):
            self.assertIs(self.proves(("triage",), "o/r"), False, "a reader that cannot run did not refuse the push with False")


class MergeRoleFault(SessionRoleCase):
    """merge/merge.py read_merge_role: when the local role reader raises, the merge reads no role, and the read does not crash.
    The case lives here because the mutation run selects the hooks suites for merge/merge.py, not merge/test_merge.py."""

    def test_the_merge_role_read_gives_no_role_when_the_role_reader_raises(self):
        sys.path.insert(0, os.path.join(HERE, "..", "merge"))
        import merge as merge_tool  # noqa: E402  merge/merge.py, the merge tool's own reader
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": SID}), \
                mock.patch.object(session_role, "own_role", side_effect=RuntimeError("injected")):
            # the local branch runs only with no cloud id; a cloud id reads its own file and never calls the role reader
            os.environ.pop("CLAUDE_CODE_REMOTE", None)
            os.environ.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
            try:
                role = merge_tool.read_merge_role()
            except Exception as e:  # a crash in the fallback is a failed assert here, not an error
                self.fail("a role reader that raised crashed the merge's role read: %r" % (e,))
        self.assertIsNone(role, "a role reader that raised gave the merge a role")


if __name__ == "__main__":
    unittest.main(verbosity=2)
