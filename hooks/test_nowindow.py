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
- On Windows the wrapper also sets stdin=DEVNULL when the caller gives no stdin (or stdin=None) and no input,
  unless this process's stdin is a pipe or a file; then stdin stays unset. When the wrapper sets that empty stdin,
  check_output drops input=None. A no-window child cannot use an inherited console stdin. The suite patches fstat(0) for the type.
- Elsewhere the wrapper adds no creationflags key. The kwargs reach subprocess unchanged.
"""
import contextlib
import importlib.util
import os
import stat
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
def on_platform(windows, stdin_mode=stat.S_IFCHR):
    """Patch the platform, and this process's stdin type as fstat(0) reads it: a console by default."""
    name, plat = ("nt", "win32") if windows else ("posix", "linux")
    real_fstat = os.fstat
    fstat = lambda fd: os.stat_result((stdin_mode,) + (0,) * 9) if fd == 0 else real_fstat(fd)  # noqa: E731
    with mock.patch.object(os, "name", name), mock.patch.object(sys, "platform", plat), \
            mock.patch.object(os, "fstat", fstat):
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

    def test_windows_gives_an_empty_stdin_when_the_caller_names_none(self):
        # A no-window child's inherited console stdin is an invalid handle: its own subprocess calls hit WinError 6.
        for name in WRAPPERS:
            with self.subTest(wrapper=name):
                rec = self.recorder(name)
                with on_platform(True):
                    getattr(self.h, name)(["x"])
                self.assertIs(rec.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

    def test_windows_treats_stdin_none_as_no_stdin(self):
        rec = self.recorder("run")
        with on_platform(True):
            self.h.run(["x"], capture_output=True, stdin=None)  # a caller forwarding an optional stdin
        self.assertIs(rec.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_windows_keeps_the_callers_stdin_and_input(self):
        rec = self.recorder("run")
        with on_platform(True):
            self.h.run(["x"], stdin=subprocess.PIPE)
        self.assertIs(rec.call_args.kwargs["stdin"], subprocess.PIPE)
        with on_platform(True):
            self.h.run(["x"], input="data")
        self.assertNotIn("stdin", rec.call_args.kwargs)  # subprocess.run refuses stdin= beside input=
        self.assertEqual(rec.call_args.kwargs["input"], "data")
        with on_platform(True):
            self.h.run(["x"], input="")  # an empty input still sets stdin itself
        self.assertNotIn("stdin", rec.call_args.kwargs)
        with on_platform(True):
            self.h.run(["x"], input=None)  # no input: the child needs a valid stdin
        self.assertIs(rec.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_windows_check_output_with_input_none_names_no_input_beside_stdin(self):
        # check_output turns input=None into "", and subprocess refuses input beside stdin.
        rec = self.recorder("check_output")
        with on_platform(True):
            self.h.check_output(["x"], input=None)
        self.assertIs(rec.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("input", rec.call_args.kwargs)

    def test_windows_passes_a_piped_or_file_stdin_through(self):
        # `printf x | verdict cmd` and `verdict cmd < file` must feed cmd; only a console stdin is replaced.
        for mode in (stat.S_IFIFO, stat.S_IFREG):
            with self.subTest(mode=oct(mode)):
                rec = self.recorder("run")
                with on_platform(True, stdin_mode=mode):
                    self.h.run(["x"], stdout=subprocess.PIPE)
                self.assertNotIn("stdin", rec.call_args.kwargs)
                rec = self.recorder("check_output")
                with on_platform(True, stdin_mode=mode):
                    self.h.check_output(["x"], input=None)
                self.assertEqual(rec.call_args.kwargs.get("input", "absent"), None)  # empty input, as on POSIX
                self.assertNotIn("stdin", rec.call_args.kwargs)

    def test_windows_unreadable_stdin_becomes_empty(self):
        rec = self.recorder("run")

        def no_stdin(fd):
            raise OSError(9, "Bad file descriptor")
        with on_platform(True), mock.patch.object(os, "fstat", no_stdin):
            self.h.run(["x"])
        self.assertIs(rec.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_posix_check_output_keeps_input_none(self):
        rec = self.recorder("check_output")
        with on_platform(False):
            self.h.check_output(["x"], input=None)
        self.assertEqual(rec.call_args.kwargs, {"input": None})

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
