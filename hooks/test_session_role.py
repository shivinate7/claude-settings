#!/usr/bin/env python3
"""Cases for hooks/session_role.py, the one home of a local session's role file (lane local-tier-file). Stdlib and unittest.

    python3 hooks/test_session_role.py

Every case runs against a config directory of its own under the run folder (CLAUDE_CONFIG_DIR), so the live ~/.claude is never read.
The reader fails closed: each id, file or role that does not prove a role gives None. A refused os.replace writes no role and
leaves no temporary file. The folder is a pathlib path under the config directory.
"""
import json
import os
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
