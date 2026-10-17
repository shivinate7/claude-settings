#!/usr/bin/env python3
"""Fixture suite for the rm shim bin/rm (macOS and Linux). Run: python3 lint/test_rm_shim.py -v

bin/rm sits ahead of the real rm on PATH. With CLAUDECODE set it refuses a recursive delete of /,
the home folder, the cwd or a parent of the cwd, and execs the real rm for every other call. With
CLAUDECODE unset it does nothing. It reuses _rm_target_bad (guard_rm_var), the one home for the
critical-path reading. Decision rm-path-wrapper (an rm shim on PATH, active only in Claude sessions).
The install.ps1 half is out of scope.

Never runs a wide delete: HOME and the cwd are temp dirs, and the module refuses to run if the shim
under test is the real rm. RM_SHIM_UNDER_TEST overrides the shim path (red proofs on a scratch shim).
Tests live here, not in bin/: bin/ is landed on PATH.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.environ.get("RM_SHIM_UNDER_TEST") or os.path.join(ROOT, "bin", "rm")
REAL_RMS = ("/bin/rm", "/usr/bin/rm")
# Fixed paths, not `which`: in a Claude session `which rm` is the shim itself.
REAL_RM = next((p for p in REAL_RMS if os.path.exists(p)), REAL_RMS[0])
REAL_SH = "/bin/sh"


def setUpModule():
    """Stop before any case runs when the shim is the real rm (a hard link or a symlink counts)."""
    if not os.path.exists(SHIM):
        return  # each case then fails on its own, with the missing-shim message
    for real in REAL_RMS:
        if os.path.exists(real) and (os.path.realpath(SHIM) == os.path.realpath(real) or os.path.samefile(SHIM, real)):
            raise RuntimeError("refusing to run: %s is the real rm (%s)" % (SHIM, real))


def names_a_delete_of(text, target):
    """True when the text offers a runnable delete of target as a remedy: a delete command (flags, then
    the target) that starts a line or follows a cue such as run, try, use or instead. The target may carry
    trailing slashes or quotes. Prose such as `rm: refusing '/'` and an echo of the refused call do not count."""
    cmd = r"""(?:/bin/rm|rm|rmdir|unlink)\s+(?:-\S+\s+)*["']?""" + re.escape(target) + r"""/*["']?(?=$|[\s`'")\;&|])"""
    cue = r"""^[ \t]*(?:[$>#][ \t]*)?|\b(?:run|try|use|instead|then|retry|with|bypass)\b[^\n]*?[\s`'"(:]"""
    return re.search("(?:" + cue + ")" + cmd, text, re.M | re.I) is not None


@unittest.skipIf(os.name == "nt", "posix shim; the install.ps1 half is a separate brief")
class Shim(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="rm-shim-"))  # realpath: /var is a symlink on macOS
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.path("home")                  # the fake HOME
        self.work = self.path("work")                  # parent of the cwd
        self.cwd = self.path("work", "proj")
        self.sub = self.path("sub")                    # a safe target, beside HOME and the cwd
        for rel in ("home/keep.txt", "home/docs/a.txt", "work/keep.txt", "work/proj/keep.txt",
                    "work/proj/file.txt", "work/proj/build/out.o", "sub/inner.txt"):
            self.touch(rel)
        self.link = os.path.join(self.cwd, "homelink")  # a symlink that points at HOME
        os.symlink(self.home, self.link)
        self.live = [self.path(*r.split("/")) for r in (
            "home/keep.txt", "home/docs/a.txt", "work/keep.txt", "work/proj/keep.txt",
            "work/proj/file.txt", "work/proj/build/out.o", "sub/inner.txt")]

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)

    def touch(self, rel):
        p = self.path(*rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("x")

    def env(self, claude=True, path=None):
        """The fake HOME, and CLAUDECODE only when claude. path replaces PATH when given."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        env["HOME"] = self.home
        if claude:
            env["CLAUDECODE"] = "1"
        if path is not None:
            env["PATH"] = path
        return env

    def run_in(self, argv, timeout=30, **kw):
        """subprocess.run, and a timeout is a failure: a shim that execs itself in a loop never exits."""
        try:
            return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, **kw)
        except subprocess.TimeoutExpired:
            self.fail("no exit within %ss (a loop?): %s" % (timeout, argv))

    def rm(self, *args, claude=True, shim=None, path=None, timeout=30):
        """Run the shim in the cwd with the fake HOME. claude=False leaves CLAUDECODE unset."""
        shim = shim or SHIM
        self.assertTrue(os.access(shim, os.X_OK), "%s is missing or not executable" % shim)
        return self.run_in([shim, *args], timeout=timeout, cwd=self.cwd, env=self.env(claude, path))

    def bindir(self, name, **tools):
        """A new folder of symlinks: bindir("x", rm="/bin/rm") holds x/rm -> /bin/rm."""
        d = self.path(name)
        os.mkdir(d)
        for tool, target in tools.items():
            os.symlink(target, os.path.join(d, tool))
        return d

    def assertIntact(self):
        gone = [p for p in self.live + [self.link] if not os.path.lexists(p)]
        self.assertEqual(gone, [], "a refused call deleted: %s" % gone)

    def assertRefused(self, args, bad):
        self.assertRefusal(self.rm(*args), args, bad)

    def assertRefusal(self, r, args, bad):
        """Nonzero exit, nothing deleted, a printed reason, and no remedy that is a delete of a forbidden
        target (rule git-remedy-never-names-target). bad lists the forbidden targets as the call named them."""
        msg = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, "exit 0 on %s: %s" % (args, msg))
        self.assertIntact()
        self.assertTrue(msg.strip(), "a refusal prints why: %s" % (args,))
        for b in bad:
            for name in {b, os.path.realpath(os.path.join(self.cwd, b))}:
                self.assertFalse(names_a_delete_of(msg, name), "the remedy names the target %r: %s" % (name, msg))

    # CLAUDECODE=1: these refuse.

    def test_refuses_root(self):
        self.assertRefused(["-rf", "/"], ["/"])

    def test_root_refuses_the_whole_call(self):
        # The real rm refuses "/" by itself, so a bare `rm -rf /` cannot show that the shim ran. A safe
        # path ahead of "/" must survive: the shim stops before the real rm deletes anything.
        self.assertRefused(["-rf", self.sub, "/"], ["/"])

    def test_refuses_home_in_every_flag_spelling(self):
        for label, args in (("-rf", ["-rf", self.home]), ("-r -f", ["-r", "-f", self.home]),
                            ("-fr", ["-fr", self.home]), ("-Rf", ["-Rf", self.home]),
                            ("long flags", ["--recursive", "--force", self.home]),
                            ("after --", ["-rf", "--", self.home]),
                            ("flag after the operand", [self.home, "-rf"])):
            with self.subTest(label):
                self.assertRefused(args, [self.home])

    def test_refuses_home_written_with_a_slash(self):
        # The shell turns `rm -rf ~/` into HOME plus a slash before rm runs, so that is what arrives.
        self.assertRefused(["-rf", self.home + "/"], [self.home, self.home + "/"])

    def test_refuses_the_cwd(self):
        for arg in (".", self.cwd, self.cwd + "/", "./", self.cwd + "/."):
            with self.subTest(arg):
                self.assertRefused(["-rf", arg], [arg])
        self.assertRefused(["-r", "-f", self.cwd], [self.cwd])

    def test_refuses_a_parent_of_the_cwd(self):
        # `..` and a trailing `..` are refused by the real rm itself, so the absolute parents below are
        # the cases that show the shim ran.
        for arg in ("..", "../..", self.work, self.work + "/", self.tmp):
            with self.subTest(arg):
                self.assertRefused(["-rf", arg], [arg])

    def test_refuses_a_relative_path_that_resolves_to_a_critical_one(self):
        for arg in ("../proj", "../../home"):
            with self.subTest(arg):
                self.assertRefused(["-rf", arg], [arg])

    def test_refuses_a_symlink_that_points_at_home(self):
        for arg in ("homelink", "homelink/", self.link):
            with self.subTest(arg):
                self.assertRefused(["-rf", arg], [arg, self.home])

    def test_a_removed_cwd_still_refuses_home(self):
        # A session's shell can sit in a folder that another command removed. getcwd then fails, but an
        # absolute HOME is still HOME: the shim must refuse, not fall open to the real rm.
        doomed = self.path("doomed")
        os.mkdir(doomed)
        self.assertTrue(os.access(SHIM, os.X_OK), "%s is missing or not executable" % SHIM)
        script = 'cd "$1" && rmdir "$1" && echo armed && "$2" -rf "$3"'
        r = self.run_in([REAL_SH, "-c", script, "sh", doomed, SHIM, self.home], env=self.env())
        self.assertIn("armed", r.stdout, "the shell's folder was not removed under it: " + r.stderr)
        self.assertRefusal(r, ["-rf", self.home], [self.home])

    # CLAUDECODE=1: these pass and delete.

    def test_passes_a_build_folder(self):
        r = self.rm("-rf", "./build")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.path("work", "proj", "build")))
        self.assertTrue(os.path.exists(self.path("work", "proj", "keep.txt")))

    def test_passes_a_plain_file(self):
        r = self.rm("file.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.path("work", "proj", "file.txt")))
        self.assertTrue(os.path.exists(self.path("work", "proj", "keep.txt")))

    def test_passes_a_safe_folder_by_absolute_path(self):
        r = self.rm("-rf", self.sub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.sub))
        self.assertTrue(os.path.exists(self.path("home", "keep.txt")))

    # CLAUDECODE unset: the shim does nothing.

    def test_unset_passes_a_safe_folder(self):
        r = self.rm("-rf", self.sub, claude=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.sub))

    def test_unset_does_not_refuse_the_fake_home(self):
        # The case above cannot go red on a shim that ignores the gate: its target is safe anyway.
        # The owner ruling (2026-10-11): outside a Claude session the shim must do nothing.
        r = self.rm("-rf", self.home, claude=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.home))

    def test_unset_needs_nothing_but_the_real_rm_and_sh_on_path(self):
        # A PATH with no python3: the shim must still hand the call to the real rm. Exit 127 means the
        # shebang's interpreter was not found, so a Claude-free shell lost its rm.
        bins = self.bindir("realbin", rm=REAL_RM, sh=REAL_SH)
        r = self.rm("file.txt", claude=False, path=bins)
        self.assertEqual(r.returncode, 0, "exit %s: %s" % (r.returncode, r.stderr))
        self.assertFalse(os.path.exists(self.path("work", "proj", "file.txt")))

    # Pass-through: calls the shim does not judge reach the real rm unchanged.

    def test_two_shim_copies_on_path_do_not_loop(self):
        # A cloud install copies bytes instead of linking, so PATH can hold two copies of the shim. Neither
        # is the other's real path, so "the next rm that is not me" must not pick the other copy.
        a, b = self.path("A"), self.path("B")
        for d in (a, b):
            os.mkdir(d)
            shutil.copy2(SHIM, os.path.join(d, "rm"))
        real = self.bindir("C", rm=REAL_RM, sh=REAL_SH)
        py = os.path.dirname(shutil.which("python3") or sys.executable)  # after the real rm, so it never wins
        path = os.pathsep.join([a, b, real, py])
        r = self.rm("file.txt", shim=os.path.join(a, "rm"), path=path, timeout=5)
        self.assertEqual(r.returncode, 0, "exit %s: %s" % (r.returncode, r.stderr))
        self.assertFalse(os.path.exists(self.path("work", "proj", "file.txt")))

    def test_a_missing_file_gives_the_real_rm_exit_code(self):
        want = self.run_in([REAL_RM, "nosuch.txt"], cwd=self.cwd, env=self.env(claude=False)).returncode
        self.assertNotEqual(want, 0)
        r = self.rm("nosuch.txt")
        self.assertEqual(r.returncode, want, r.stderr)
        self.assertIntact()

    def test_a_file_named_with_a_dash_is_deleted_after_dashes(self):
        self.touch("work/proj/-dash")
        r = self.rm("--", "-dash")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.path("work", "proj", "-dash")))
        self.assertIntact()


if __name__ == "__main__":
    unittest.main()
