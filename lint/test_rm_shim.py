#!/usr/bin/env python3
"""Fixture suite for the rm shim bin/rm (macOS and Linux). Run: python3 lint/test_rm_shim.py -v

bin/rm sits ahead of the real rm on PATH. With CLAUDECODE set it refuses a recursive delete of /,
the home folder, the cwd or a parent of the cwd, and execs the real rm for every other call. With
CLAUDECODE unset it does nothing. It reuses _rm_target_bad (guard_rm_var), the one home for the
critical-path reading. Decision rm-path-wrapper (an rm shim on PATH, active only in Claude sessions).
The install.ps1 half is out of scope.

On Git Bash, MSYS2 and Cygwin (uname -s starts MINGW, MSYS or CYGWIN) the shim execs the real rm before
it looks for python: each python start there costs two more processes. Elsewhere it finds python like
the hook launchers in settings.json: python3, then python, skipping a path under WindowsApps (the
Microsoft Store alias). These cases stub uname and python on a PATH of their own, so any host runs them.

Never runs a wide delete: HOME and the cwd are temp dirs, and the module refuses to run if the shim
under test is the real rm. RM_SHIM_UNDER_TEST overrides the shim path (red runs on a scratch shim).
Tests live here, not in bin/: bin/ is landed on PATH.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.environ.get("RM_SHIM_UNDER_TEST") or os.path.join(ROOT, "bin", "rm")
REAL_RMS = ("/bin/rm", "/usr/bin/rm")
# Fixed paths, not `which`: in a Claude session `which rm` is the shim itself.
REAL_RM = next((p for p in REAL_RMS if os.path.exists(p)), REAL_RMS[0])
REAL_SH = "/bin/sh"
REAL_CAT = next((p for p in ("/bin/cat", "/usr/bin/cat") if os.path.exists(p)), "/bin/cat")
WINDOWS_UNAMES = ("MINGW64_NT-10.0-26200", "MSYS_NT-10.0-26200", "CYGWIN_NT-10.0-26200")
PY_ALIAS = "exit 9"  # the Store alias: it prints a pointer to the Store and exits
PY_REAL = 'exec "%s" "$@"' % sys.executable
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1")


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


def sh_code(text):
    """The part of an sh script that the shell runs or expands: # comments, single-quoted text and quoted
    here-document bodies are dropped. One pass over quotes, comments and here-documents, so a quote inside
    a comment or a here-document opens no string, and a # inside a string opens no comment."""
    out, q, doc = [], None, None  # q: the open quote; doc: (tag, body expands) inside a here-document
    for line in text.splitlines(True):
        if doc:
            if line.strip() == doc[0]:
                doc = None
            elif doc[1]:
                out.append(line)
            continue
        i = 0
        while i < len(line):
            c = line[i]
            if c == "\\" and q != "'":
                out.append(line[i:i + 2])
                i += 2
                continue
            if q:
                if c == q:
                    q = None
                elif q == '"':
                    out.append(c)
            elif c in "'\"":
                q = c
            elif c == "#" and (i == 0 or line[i - 1] in " \t;|&("):
                out.append("\n")
                break
            else:
                m = HEREDOC.match(line, i) if line.startswith("<<", i) and line[i - 1:i] != "<" else None
                if m:
                    doc = (m.group(2), not m.group(1))
                    out.append(line[i:m.end()])
                    i = m.end()
                    continue
                out.append(c)
            i += 1
    return "".join(out)


def forks_cat(text):
    """True when the sh script runs a command substitution of cat: $(cat ...) or `cat ...`."""
    return re.search(r"\$\(\s*cat\b|`\s*cat\b", sh_code(text)) is not None


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

    def exe(self, d, name, body):
        """A stub d/name: an sh script that runs body. d is made when it is missing."""
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\n" + body + "\n")
        os.chmod(p, 0o755)

    def recorder(self, d, name, tail="exit 0"):
        """A stub d/name that appends its own path to calls.log in the parent of d, and then runs tail."""
        log = os.path.join(os.path.dirname(d), "calls.log")
        self.exe(d, name, "echo \"$0\" >> '%s'\n%s" % (log, tail))

    def calls(self, root):
        """The paths of the stubs that ran under root, oldest first."""
        try:
            with open(os.path.join(root, "calls.log")) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

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

    def test_a_refusal_says_that_no_override_lifts_it(self):
        # The shim runs inside the command, after the guard, so an owner override cannot reach it
        # (decision owner-override). The refusal says so, in place of leaving the owner to type one.
        r = self.rm("-rf", "/")
        self.assertRefusal(r, ["-rf", "/"], ["/"])
        self.assertIn("no override", (r.stdout + r.stderr).lower())

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

    def test_a_file_in_the_cwd_named_like_a_stdlib_module_does_not_open_the_guard(self):
        # python3 puts the cwd on sys.path for `-c`, so a types.py there shadows the stdlib `types`. The
        # helper then fails to load, and the shim falls open to the real rm. Claude's cwd is a project
        # folder that holds files of any name; the shim must refuse HOME all the same.
        with open(self.path("work", "proj", "types.py"), "w") as f:
            f.write('raise ImportError("shadow")\n')
        self.assertRefused(["-rf", self.home], [self.home])
        self.assertTrue(os.path.isdir(self.home), "the fake HOME was deleted")

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
        # The case above cannot go red on a shim that ignores the guard: its target is safe anyway.
        # Outside a Claude session the shim must do nothing.
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

    # Windows: a recursive call under CLAUDECODE still reaches the real rm with no python.

    def test_a_windows_uname_execs_the_real_rm_and_starts_no_python(self):
        args = ["-rf", "--", "dir with space", "-weird"]
        for n, uname in enumerate(WINDOWS_UNAMES):
            with self.subTest(uname):
                root = self.path("win%d" % n)
                d = os.path.join(root, "stubs")
                seen = os.path.join(root, "rm.args")
                self.exe(d, "uname", "echo " + uname)
                self.recorder(d, "rm", "printf '%%s\\n' \"$@\" > '%s'; exit 7" % seen)
                self.recorder(d, "python3")
                self.recorder(d, "python")
                r = self.rm(*args, path=d)
                started = [c for c in self.calls(root) if "/python" in c]
                self.assertEqual(started, [], "python started under uname %s" % uname)
                self.assertEqual(self.calls(root), [os.path.join(d, "rm")])
                with open(seen) as f:
                    self.assertEqual(f.read().splitlines(), args)
                self.assertEqual(r.returncode, 7, "the real rm's exit code is the call's: " + r.stderr)

    # Elsewhere: python3, then python; a path under WindowsApps is the Store alias and is skipped.

    def python_lookup(self, store_stubs, ok_stubs, want):
        """Run the shim on a PATH of two folders, WindowsApps then ok. Each stub is name -> its body. The stub
        named want must be the only python that runs, and the interpreter behind it must refuse HOME. With
        want None no python is usable: none runs, and the real rm still deletes."""
        root = self.path("py")
        os.mkdir(root)
        store = self.bindir("py/WindowsApps")
        ok = self.bindir("py/ok", rm=REAL_RM, cat=REAL_CAT)
        self.exe(ok, "uname", "echo Linux")
        for d, stubs in ((store, store_stubs), (ok, ok_stubs)):
            for tool, body in stubs.items():
                self.recorder(d, tool, body)
        r = self.rm("-rf", self.home if want else self.sub, path=os.pathsep.join([store, ok]))
        self.assertEqual(self.calls(root), [os.path.join(ok, want)] if want else [], "the python that ran")
        if want:
            self.assertRefusal(r, ["-rf", self.home], [self.home])
        else:
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.exists(self.sub), "no python: the real rm still runs")

    def test_a_store_alias_python3_is_skipped_for_python(self):
        self.python_lookup({"python3": PY_ALIAS}, {"python": PY_REAL}, "python")

    def test_python_is_used_when_there_is_no_python3(self):
        self.python_lookup({}, {"python": PY_REAL}, "python")

    def test_python3_comes_before_python(self):
        self.python_lookup({}, {"python3": PY_REAL, "python": "exit 0"}, "python3")

    def test_only_a_store_alias_means_no_python(self):
        self.python_lookup({"python3": PY_ALIAS}, {}, None)


class ShimSource(unittest.TestCase):
    def test_the_shim_runs_no_cat(self):
        # A command substitution of cat forks a subshell and a cat on every judged call. The python
        # program goes to python on stdin through a here-document instead.
        with open(SHIM) as f:
            text = f.read()
        self.assertIn("exec", sh_code(text), "the scanner read no code from the shim")
        self.assertFalse(forks_cat(text), "the shim runs a command substitution of cat")


class ShScanner(unittest.TestCase):
    """forks_cat reads code, not text: a comment opener in a string, a multi-line string, a lone quote."""
    FOUND = (
        ("plain", "x=$(cat f)\n"),
        ("backticks", "x=`cat f`\n"),
        ("a # in single quotes opens no comment", "echo '#'; x=$(cat f)\n"),
        ("a # in double quotes opens no comment", 'echo "#" $(cat f)\n'),
        ("$# is not a comment", "echo $# $(cat f)\n"),
        ("// and /* are not comment openers in sh", 'echo "//" "/*"; x=$(cat f)\n'),
        ("a double-quoted string expands it", 'echo "# $(cat f)"\n'),
        ("a multi-line double-quoted string expands it", 'x="a\nb $(cat f)\nc"\n'),
        ("a lone quote in a comment opens no string", "# don't\nx=$(cat f)\n"),
        ("an escaped quote opens no string", "echo it\\'s; x=$(cat f)\n"),
        ("code after a quoted here-document with a lone quote", "python3 - <<'E'\nprint(\"don't\")\nE\nx=$(cat f)\n"),
        ("an unquoted here-document expands it", "cat <<E\n$(cat f)\nE\n"),
        ("the substitution that opens a quoted here-document", "PY=$(cat <<'E'\nprint(1)\nE\n)\n"),
        ("CRLF line ends", "x=1\r\ny=$(cat f)\r\n"),
    )
    NOT_FOUND = (
        ("a comment", "# $(cat f)\n"),
        ("a trailing comment", "x=1 # $(cat f)\n"),
        ("a comment with a lone quote", "# don't $(cat f)\n"),
        ("single quotes", "echo '$(cat f)'\n"),
        ("a multi-line single-quoted string", "x='a\n$(cat f)\nc'\n"),
        ("a quoted here-document body", "python3 - <<'E'\nprint(\"don't\")\n$(cat f)\nE\n"),
        ("a quoted here-document, CRLF", "python3 - <<'E'\r\n$(cat f)\r\nE\r\n"),
        ("another command", "x=$(category f)\n"),
        ("a here-string", "python3 - <<<'$(cat f)'\n"),
    )

    def test_finds_a_command_substitution_of_cat_in_code(self):
        for label, text in self.FOUND:
            with self.subTest(label):
                self.assertTrue(forks_cat(text), repr(text))

    def test_ignores_the_same_words_in_inert_text(self):
        for label, text in self.NOT_FOUND:
            with self.subTest(label):
                self.assertFalse(forks_cat(text), repr(text))


if __name__ == "__main__":
    unittest.main()
