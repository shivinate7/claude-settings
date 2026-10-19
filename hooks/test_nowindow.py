#!/usr/bin/env python3
"""Unit suite for the no-window helper, hooks/_nowindow.py. Run: python3 hooks/test_nowindow.py -v

Pins the contract that lint/test_no_window_spawn.py relies on:
- The file is hooks/_nowindow.py and loads by path. While it is missing, every test fails with
  "module missing".
- Five drop-in wrappers: run, Popen, call, check_call, check_output. Each calls subprocess.<name> at
  call time, so a patch on subprocess.<name> sees the call, and each returns what subprocess returns.
- The platform test is read at call time: sys.platform == "win32" or os.name == "nt". This suite
  patches both signals, so the helper may read either one.
- On Windows the wrapper ORs CREATE_NO_WINDOW (0x08000000) into the caller's creationflags and keeps
  every flag the caller passed. The constant is pinned as a number, because subprocess has no
  CREATE_NO_WINDOW on the Linux CI runner.
- Elsewhere the wrapper adds no creationflags key. The kwargs reach subprocess unchanged.
"""
import contextlib
import importlib.util
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER_PATH = os.path.join(HERE, "_nowindow.py")
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
WRAPPERS = ("run", "Popen", "call", "check_call", "check_output")


def load_helper():
    if not os.path.exists(HELPER_PATH):
        raise AssertionError("module missing: hooks/_nowindow.py does not exist yet")
    spec = importlib.util.spec_from_file_location("_nowindow", HELPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def on_platform(windows):
    name, plat = ("nt", "win32") if windows else ("posix", "linux")
    with mock.patch.object(os, "name", name), mock.patch.object(sys, "platform", plat):
        yield


class HelperContract(unittest.TestCase):
    def setUp(self):
        self.h = load_helper()

    def recorder(self, name):
        rec = mock.Mock(name=name, return_value="ret-" + name)
        patcher = mock.patch.object(subprocess, name, rec)
        patcher.start()
        self.addCleanup(patcher.stop)
        return rec

    def test_constant_is_the_windows_flag(self):
        self.assertEqual(self.h.CREATE_NO_WINDOW, CREATE_NO_WINDOW)

    def test_every_wrapper_sets_the_flag_on_windows_and_returns_the_result(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                rec = self.recorder(name)
                with on_platform(True):
                    got = getattr(self.h, name)(["x"])
                self.assertEqual(got, "ret-" + name)
                rec.assert_called_once()
                self.assertEqual(rec.call_args.kwargs.get("creationflags"), CREATE_NO_WINDOW)

    def test_windows_keeps_caller_flags_by_or_not_replacement(self):
        rec = self.recorder("run")
        with on_platform(True):
            self.h.run(["x"], creationflags=DETACHED_PROCESS, capture_output=True)
        self.assertEqual(rec.call_args.kwargs["creationflags"], CREATE_NO_WINDOW | DETACHED_PROCESS)
        self.assertIs(rec.call_args.kwargs["capture_output"], True)

    def test_windows_keeps_a_second_caller_flag(self):
        rec = self.recorder("Popen")
        with on_platform(True):
            self.h.Popen(["x"], creationflags=CREATE_NEW_PROCESS_GROUP)
        self.assertEqual(rec.call_args.kwargs["creationflags"], CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)

    def test_posix_sets_no_creationflags_key(self):
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                rec = self.recorder(name)
                with on_platform(False):
                    getattr(self.h, name)(["x"], capture_output=True)
                self.assertEqual(rec.call_args.kwargs, {"capture_output": True})

    def test_posix_passes_caller_creationflags_unchanged(self):
        rec = self.recorder("run")
        with on_platform(False):
            self.h.run(["x"], creationflags=DETACHED_PROCESS)
        self.assertEqual(rec.call_args.kwargs, {"creationflags": DETACHED_PROCESS})


if __name__ == "__main__":
    unittest.main()
