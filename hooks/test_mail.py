#!/usr/bin/env python3
"""Cases for the git mailbox: bin/mail (send, read, take) and hooks/mail.py (turn_start_lines).

Run it from the repository root:

    python3 hooks/test_mail.py

Standard library only, and no test runner. Each case runs against a bare store on a file:// URL
(MAILBOX_REPO) with one scratch cache per machine (MAILBOX_CACHE). No case sleeps or reads the clock.

Contract the builder codes against. Each case asserts one named cause. Pinned choice 11 lists the cases
that pass on the base commit, and why each stays.
- bin/mail send --to <addr> --kind request|inform|reply [--re <id>] --body-file F
  The sender's address is cloud/<CLAUDE_CODE_REMOTE_SESSION_ID>. It writes mail/<addr>/<id>.md on
  refs/heads/mail with plumbing only, never a working tree. It exits 0 only when the pushed tip's tree holds
  that file and no path in the tree holds a CR. Otherwise it exits 1 with "not sent: <reason>", and the mail
  ref does not move.
- bin/mail read [<id>]  prints the open messages, or one message with its body. With no --addr, the open
  messages of the session's own folder (CLAUDE_CODE_SESSION_ID locally) are listed too.
- bin/mail take <id>    one commit moves mail/<addr>/<id>.md to done/<addr>/<id>.md with a
  Taken-by: line. A taker that finds the path gone prints "taken by another" and exits non-zero.
- hooks/mail.py turn_start_lines(payload, env) -> list[str]. payload carries session_id and cwd;
  env carries MAILBOX_REPO, MAILBOX_CACHE and CLAUDE_CODE_REMOTE_SESSION_ID. Failure lines start
  "mail unknown: " and never say "no mail".
- A message file has line 1 `Msg <id> from <addr> to <addr> kind <kind> re <id|-> try <n>`, line 2
  `Reply-to: <addr>`, then the body. The fixtures write this format with plumbing.

Pinned choices (each one a departure or an open point, not settled by the spec):
1. Retry trigger. A push is retried only after a non-fast-forward, at most 5 retries, so 6 pushes
   in all. Any other refused push prints "not sent: <reason>" at once and exits 1. Item 153 on the git
   mailbox page sets this: push retry on non-fast-forward only, at most 5 retries.
2. A non-fast-forward on every try. Git forbids ref updates inside a pre-receive hook, and a
   server refusal reads "[remote rejected]", so the case pushes to a second store whose tip the
   sender never fetched. The client refuses each push itself, as "[rejected]", before it sends
   anything. Pushes are counted from the trace2 event log of the send.
3. An unchanged turn still lists open mail, from a listing the moved turn wrote. Its one git start
   is the remote check, and the turn writes no file.
4. A request stays listed after its reply lands, until take. An inform closes by take alone; that
   case asserts that take removes it from turn start and creates nothing else.
5. The pc/<host> form is covered in-process. The checkout gets an origin URL, and socket.gethostname is
   patched to a fixed host. The CLI subprocess sees the real host, so the --addr cases pass the address.
6. The sweep of old run folders is proven in hooks/test_feedback_inbox.py. Not repeated here.
7. A stand-in git (a script named git, first on the case's PATH) stands in for the git calls of one machine.
   It logs each call's env, fails a named subcommand, drops a named update-index (its stdin is read and
   dropped, exit 0), feeds an update-index --index-info CRLF lines (the "crlf" action), feeds a hash-object
   --stdin CRLF lines (the "crlf-stdin" action), drops the removal lines of an update-index --index-info (the
   "drop-removal" action), or runs an interloper once before its push, then execs the real git. Each
   intercepting action writes a marker file, and its case asserts the marker, so an unrun stub fails the case.
   ReadShowFails, PushRefusedRetry, TakeBothFromOneTip, PromptEnv, IndexUpdateDropped, CrlfIndexLines,
   CrlfBlobHashed and TakeRemovalDropped use it. The stub is an extensionless POSIX script, and Windows
   CreateProcess never runs such a file, so those cases skip on Windows with that reason.
8. Timeouts. Each git call of a turn start carries its own bound. The bounds of one moved turn sum to
   10 s or less: fixed per-step bounds, the worst case where every step runs its full bound. The case
   pins that shape. A shared-deadline build passes each call the time left, so its recorded bounds
   shrink and sum past 10; that build needs this case re-pointed. A build that passes no timeout= fails
   the no-None check. The case reads no clock (P5).
9. A hang is simulated. Starts raises subprocess.TimeoutExpired for a named git subcommand, the exception
   a real bound raises, so no case waits out a bound.
10. Cloud ids: CLAUDE_CODE_REMOTE_SESSION_ID cse_<x> is the address cloud/session_<x>. The older cases keep
   plain ids such as sess-b, which the cse_ mapping must not change.
11. Cases that pass on the base commit. Each is a regression guard for its named claim, and each has a
   mutant check (the mutant is a copy of the built code with one change; it is not in the repo):
   PushRefusedRetry (retries set to 1: "not sent", exit 1), TakeBothFromOneTip (a lost push read as a win:
   the second taker prints taken), TakeSameSecond (the nonce removed from the Taken-by line: both takers
   print taken), SshBatchDefault (the default removed: its two default cases go red) and AgeUnknown (the
   fallback removed: the message is not listed), ReadBackFromTip (a CRLF blob from hash-object's stdin: its
   body and no-CR checks go red), IndexUpdateDropped and CrlfIndexLines (the send's read-back refuses a
   dropped or CRLF index update: the clause or check that refuses goes red) and TakeRemovalDropped (the
   removal clause of the take read-back: with it removed, the take prints taken). TakeBothFromOneTip gives
   its two machines distinct git identities. TakeSameSecond keeps one identity and one address, and pins
   the clock, so two takers build the same commit unless the Taken-by line carries a nonce.
12. Local read. `bin/mail read` with no --addr takes its session folder from CLAUDE_CODE_SESSION_ID.
   LocalSessionRead runs bin/mail's main in this process with the host set to PC_HOST, since the CLI
   subprocess sees the real host.
13. Stdin that is not UTF-8 is refused: "not sent: body is not UTF-8" and exit 1. bin/mail reads stdin as strict
   UTF-8, so a lone surrogate never reaches git(). StdinNotUtf8 pins it.
14. A git call that reports "Ignoring path" on stderr and exits 0 is an error. The stub kind warn keeps every
   index entry and writes the warning to stderr. IgnoredPathStderr pins that the send then says not sent.
   Any other stderr line is not an error: the same class's allow case pins that the send still prints sent.

Every machine gets a git identity, as a configured Mac does. A machine with no identity is not covered.
"""
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(REPO, "testing"))
import tracked_tree  # noqa: E402  rm_tree clears the read-only bit of git objects (testing/tracked_tree.py)

ROOT = _test_temp.run_folder()
MAIL_CLI = os.path.join(REPO, "bin", "mail")
MAIL_HOOK = os.path.join(REPO, "hooks", "mail.py")
REFUSED = "refs/heads/mail"
SCRUBBED = ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "MAILBOX_REPO",
            "MAILBOX_CACHE", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SSH", "GIT_SSH_COMMAND", "CLAUDE_CODE_EXECPATH", "AI_AGENT",
            "MAILBOX_HOLD_OFF", "MAILBOX_REFRESH_COMMAND")
IDENTITY = {"GIT_AUTHOR_NAME": "Mail Test", "GIT_AUTHOR_EMAIL": "mail-test@example.invalid",
            "GIT_COMMITTER_NAME": "Mail Test", "GIT_COMMITTER_EMAIL": "mail-test@example.invalid"}
# A second machine's identity. Two takers with one identity and one address can build byte-identical
# take commits in the same second, so a race case gives its two machines different identities.
OTHER_IDENTITY = {"GIT_AUTHOR_NAME": "Mail Other", "GIT_AUTHOR_EMAIL": "mail-other@example.invalid",
                  "GIT_COMMITTER_NAME": "Mail Other", "GIT_COMMITTER_EMAIL": "mail-other@example.invalid"}
UNKNOWN = "mail unknown: "
# The refresh notice of a repo whose origin is ORIGIN (decision merge-mail-refreshes-sessions): its path and its body.
REFRESH_PATH = "mail/refresh/acme-widgets/main.md"
SHA_A, SHA_B = "a" * 40, "b" * 40
# Git's author and committer dates and the Taken-by stamp are pinned, so two takers in one case build one commit.
SAME_SECOND = {"GIT_AUTHOR_DATE": "1800000000 +0000", "GIT_COMMITTER_DATE": "1800000000 +0000"}
PINNED_STAMP = "2026-01-01T00:00:00Z"
REAL_GIT = shutil.which("git")  # resolved before any case edits PATH: the stand-in execs this
ORIGIN = "https://github.com/acme/widgets.git"  # the pc slug is acme-widgets
PC_HOST = "box-one"
PC_BASE = "pc/box-one/acme-widgets"
# The one skip reason of every case that needs the stand-in git. Windows CreateProcess runs no extensionless file.
NT_NO_STUB = ("the stand-in git is an extensionless script, which Windows CreateProcess never runs, "
              "so git is not intercepted on Windows")
# The stand-in git. @PYTHON@, @CONF@ and @REAL@ are filled in by Machine.install_stub.
STUB = """#!@PYTHON@
import json, os, subprocess, sys
CONF = @CONF@
REAL = @REAL@
WATCH = ("GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE")


def subcommand(argv):
    rest = list(argv)
    while rest and rest[0] in ("-c", "-C", "--git-dir", "--work-tree"):
        rest = rest[2:]
    return rest[0] if rest else None


with open(CONF, encoding="utf-8") as handle:
    conf = json.load(handle)
args = sys.argv[1:]
sub = subcommand(args)


def mark():
    if conf.get("marker"):
        open(conf["marker"], "w").close()


if conf.get("log"):
    with open(conf["log"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"sub": sub, "env": {k: os.environ.get(k) for k in WATCH}}) + "\\n")
action = (conf.get("actions") or {}).get(sub)
if action and action["kind"] == "fail":
    sys.stderr.write(action["stderr"] + "\\n")
    sys.exit(128)
if action and action["kind"] == "drop":
    if "--index-info" in args:
        mark()
        sys.stdin.buffer.read()
    sys.exit(0)
if action and action["kind"] == "crlf" and "--index-info" in args:
    mark()
    done = subprocess.run([REAL] + args, input=sys.stdin.buffer.read().replace(b"\\n", b"\\r\\n"))
    sys.exit(done.returncode)
if action and action["kind"] == "crlf-stdin" and "--stdin" in args:
    mark()
    done = subprocess.run([REAL] + args, input=sys.stdin.buffer.read().replace(b"\\n", b"\\r\\n"))
    sys.exit(done.returncode)
if action and action["kind"] == "drop-removal" and "--index-info" in args:
    mark()
    kept = [line for line in sys.stdin.buffer.read().splitlines(True) if not line.startswith(b"0 ")]
    done = subprocess.run([REAL] + args, input=b"".join(kept))
    sys.exit(done.returncode)
if action and action["kind"] == "warn" and "--index-info" in args:
    # The real git runs on the same stdin, so every entry lands. Its stderr gets the warning, and the exit code stays.
    mark()
    data = sys.stdin.buffer.read()
    done = subprocess.run([REAL] + args, input=data, capture_output=True)
    sys.stdout.buffer.write(done.stdout)
    sys.stderr.buffer.write(done.stderr + action["stderr"].encode("utf-8"))
    sys.exit(done.returncode)
if action and action["kind"] == "before" and not os.path.exists(action["once"]):
    open(action["once"], "w").close()
    done = subprocess.run(action["argv"], env=action["env"], capture_output=True, text=True)
    with open(action["record"], "w", encoding="utf-8") as handle:
        json.dump({"code": done.returncode, "out": done.stdout + done.stderr}, handle)
os.execv(REAL, [REAL] + args)
"""


def load_hook():
    """hooks/mail.py when it exists. Absent, the cases see a stub that reports nothing, so each
    case fails on its own outcome assert. A file that exists but fails to import raises."""
    if not os.path.exists(MAIL_HOOK):
        return None
    spec = importlib.util.spec_from_file_location("mail_under_test", MAIL_HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAIL_MODULE = load_hook()


def turn_start_lines(payload, env):
    fn = getattr(MAIL_MODULE, "turn_start_lines", None)
    return [] if fn is None else fn(payload, env)


def scrubbed_environ():
    env = {key: value for key, value in os.environ.items() if key not in SCRUBBED}
    env["MAILBOX_HOLD_OFF"] = "1"  # a case never depends on the host platform; MacHold removes it
    return env


def fixture_env(home, extra=None):
    """The env the fixture git calls run in: a scratch home, the identity, no prompts."""
    env = scrubbed_environ()
    env.update(IDENTITY)
    env.update({"HOME": home, "USERPROFILE": home, "XDG_CONFIG_HOME": home,
                "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
    env.update(extra or {})
    return env


def git(cwd, args, env, input_text=None, binary=False):
    """binary=True returns bytes. Text mode turns a lone CR into a newline, and the CRLF cases look for that CR."""
    if isinstance(input_text, bytes):
        # Text-mode stdin on Windows turns each LF into CRLF, so a CRLF fixture would reach git as CR CR LF.
        result = subprocess.run(["git", *args], cwd=cwd, env=env, input=input_text, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError("fixture git %s failed: %s" % (args[0], result.stderr.decode("utf-8", "replace").strip()))
        return result.stdout if binary else result.stdout.decode("utf-8", "replace")
    mode = {} if binary else {"text": True, "encoding": "utf-8", "errors": "replace"}
    result = subprocess.run(["git", *args], cwd=cwd, env=env, input=input_text,
                            capture_output=True, timeout=60, **mode)
    if result.returncode:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode("utf-8", "replace")
        raise RuntimeError("fixture git %s failed: %s" % (args[0], stderr.strip()))
    return result.stdout


def message_id(path):
    return os.path.splitext(os.path.basename(path))[0]


class Store:
    """A bare repo on a file:// URL, the MAILBOX_REPO of every machine in one case."""

    def __init__(self, case, name="store"):
        self.path = os.path.join(case, name + ".git")
        self.env = fixture_env(os.path.join(case, "fixture-home"))
        git(case, ["init", "--bare", "-q", self.path], self.env)
        self.url = Path(self.path).as_uri()

    def tip(self):
        result = subprocess.run(["git", "rev-parse", "-q", "--verify", REFUSED], cwd=self.path,
                                env=self.env, capture_output=True, text=True, timeout=60)
        return result.stdout.strip() or None

    def files(self, prefix="", raw=False):
        """The tip's paths that start with prefix, sorted. raw=True reads them with -z: git C-quotes a path with
        a CR in text output, so only the raw listing shows that CR."""
        tip = self.tip()
        if tip is None:
            return []
        if raw:
            listing = git(self.path, ["ls-tree", "-r", "-z", "--name-only", tip], self.env, binary=True)
            paths = [path.decode("utf-8") for path in listing.split(b"\0") if path]
        else:
            paths = git(self.path, ["ls-tree", "-r", "--name-only", tip], self.env).splitlines()
        return sorted(path for path in paths if path.startswith(prefix))

    def read(self, path, raw=False):
        """The blob at path on the tip. raw=True returns bytes, so a CR in the content survives."""
        if raw:
            return git(self.path, ["cat-file", "blob", "%s:%s" % (self.tip(), path)], self.env, binary=True)
        return git(self.path, ["show", "%s:%s" % (self.tip(), path)], self.env)

    def seed(self, addr, mid, kind, sender, body, re_id="-", eol="\n", body_eol=None):
        """Land one message on the mail ref with fixture plumbing, so a send bug cannot mask a read or take case.
        eol ends the header lines and the blank line after them; body_eol ends the body (default: eol). A line ending
        other than LF is written as bytes, so text-mode stdin on Windows does not turn each LF into CRLF."""
        body_eol = eol if body_eol is None else body_eol
        text = ("Msg %s from %s to %s kind %s re %s try 1%sReply-to: %s%s%s%s%s"
                % (mid, sender, addr, kind, re_id, eol, sender, eol, eol, body, body_eol))
        index = os.path.join(self.path, "seed.index")
        env = dict(self.env, GIT_INDEX_FILE=index)
        if os.path.exists(index):
            os.remove(index)
        tip = self.tip()
        if tip is None:
            git(self.path, ["read-tree", "--empty"], env)
        else:
            git(self.path, ["read-tree", tip], env)
        data = text.encode("utf-8") if "\r" in text else text
        blob = git(self.path, ["hash-object", "-w", "--stdin"], self.env, input_text=data).strip()
        git(self.path, ["update-index", "--add", "--cacheinfo",
                        "100644,%s,mail/%s/%s.md" % (blob, addr, mid)], env)
        tree = git(self.path, ["write-tree"], env).strip()
        commit_args = ["commit-tree", tree, "-m", "seed %s" % mid]
        if tip is not None:
            commit_args += ["-p", tip]
        commit = git(self.path, commit_args, self.env).strip()
        update = ["update-ref", REFUSED, commit] + ([tip] if tip is not None else [])
        git(self.path, update, self.env)

    def publish(self, path, text, removes=()):
        """Land one plain file at path, with no message header, as one commit on the tip, with fixture plumbing. An
        existing file at path is replaced. Each path in removes is deleted in the same commit. A refresh notice lands this
        way, so a receiver case needs no sender code."""
        tip = self.tip()
        index = os.path.join(self.path, "publish.index")
        env = dict(self.env, GIT_INDEX_FILE=index)
        if os.path.exists(index):
            os.remove(index)
        git(self.path, ["read-tree", tip] if tip is not None else ["read-tree", "--empty"], env)
        blob = git(self.path, ["hash-object", "-w", "--stdin"], self.env, input_text=text.encode("utf-8")).strip()
        git(self.path, ["update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path)], env)
        for gone in removes:
            git(self.path, ["update-index", "--force-remove", gone], env)
        tree = git(self.path, ["write-tree"], env).strip()
        commit_args = ["commit-tree", tree, "-m", "publish %s" % path]
        if tip is not None:
            commit_args += ["-p", tip]
        commit = git(self.path, commit_args, self.env).strip()
        git(self.path, ["update-ref", REFUSED, commit] + ([tip] if tip is not None else []), self.env)


class Machine:
    """One machine: its own home, its own cache, and a scratch checkout as its working directory."""

    def __init__(self, case, name, repo_url, session=None, push_to=None, trace=None, origin=None,
                 stub=False, prompt_env=True, identity=None):
        self.name = name
        self.session = session
        self.case = case
        self.home = os.path.join(case, name + "-home")
        self.cache = os.path.join(case, name + "-cache.git")
        self.checkout = os.path.join(case, name + "-checkout")
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.checkout, exist_ok=True)
        git(self.checkout, ["init", "-q"], fixture_env(self.home))
        if origin is not None:
            git(self.checkout, ["remote", "add", "origin", origin], fixture_env(self.home))
        env = scrubbed_environ()
        env.update(identity or IDENTITY)
        env.update({"HOME": self.home, "USERPROFILE": self.home, "XDG_CONFIG_HOME": self.home,
                    "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
                    "MAILBOX_REPO": repo_url, "MAILBOX_CACHE": self.cache})
        if not prompt_env:  # the product must set both itself
            for key in ("GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE"):
                env.pop(key, None)
        if session is not None:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = session
        if push_to is not None:
            add_git_config(env, "url.%s.pushInsteadOf" % push_to, repo_url)
        if trace is not None:
            env["GIT_TRACE2_EVENT"] = trace
        self.env = env
        self.stub_conf = None
        self.stub_marker = None
        if stub:
            self.install_stub()

    def install_stub(self):
        """Puts the stand-in git first on this machine's PATH. Its actions come from stub_actions."""
        folder = os.path.join(self.case, self.name + "-stub")
        os.makedirs(folder)
        self.stub_conf = os.path.join(folder, "conf.json")
        self.stub_marker = os.path.join(folder, "intercepted")
        script = os.path.join(folder, "git")
        body = (STUB.replace("@PYTHON@", sys.executable).replace("@CONF@", repr(self.stub_conf))
                .replace("@REAL@", repr(REAL_GIT)))
        with open(script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        os.chmod(script, 0o755)
        self.env["PATH"] = folder + os.pathsep + self.env.get("PATH", "")
        self.stub_actions({})

    def stub_actions(self, actions, log=None):
        """actions: {git subcommand: {"kind": "fail", "stderr": ...}
        | {"kind": "before", "once", "argv", "env", "record"}
        | {"kind": "drop" | "crlf" | "drop-removal" | "warn"} on update-index --index-info
        | {"kind": "crlf-stdin"} on hash-object --stdin}.
        log: a file that gets one line per git start (its subcommand and the two prompt variables).
        Each intercepting action writes self.stub_marker, which assert_stub_intercepted reads."""
        with open(self.stub_conf, "w", encoding="utf-8") as handle:
            json.dump({"actions": actions, "log": log, "marker": self.stub_marker}, handle)


class Starts:
    """Counts the processes started inside this block, and the timeout each git run was given. Popen covers
    subprocess.run and the no-window wrapper. `expire` names git subcommands whose run raises TimeoutExpired
    at once, the exception a hang past its bound raises, so no case waits out a bound."""

    def __init__(self, expire=()):
        self.argv = []
        self.bounds = []
        self.expire = tuple(expire)

    def __enter__(self):
        starts, bounds, expire = self.argv, self.bounds, self.expire
        real = subprocess.Popen
        real_run = subprocess.run

        class Counting(real):
            def __init__(self, args, *rest, **kwargs):
                starts.append(args)
                super().__init__(args, *rest, **kwargs)

        def counting_run(args, *rest, **kwargs):
            if program_name(args) == "git":
                bounds.append(kwargs.get("timeout"))
                if git_subcommand(args) in expire:
                    raise subprocess.TimeoutExpired(args, kwargs.get("timeout"))
            return real_run(args, *rest, **kwargs)

        self.patches = [mock.patch.object(subprocess, "Popen", Counting),
                        mock.patch.object(subprocess, "run", counting_run)]
        for patch in self.patches:
            patch.start()
        return self

    def __exit__(self, *exc):
        for patch in reversed(self.patches):
            patch.stop()
        return False

    def git_starts(self):
        return [args for args in self.argv if program_name(args) == "git"]

    def git_bounds(self):
        return list(self.bounds)


def program_name(args):
    first = args[0] if isinstance(args, (list, tuple)) else str(args).split()[0]
    base = os.path.basename(str(first)).lower()
    return base[:-4] if base.endswith(".exe") else base


def snapshot(folder):
    tree = {}
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames:
            tree[os.path.relpath(os.path.join(dirpath, name), folder) + os.sep] = None
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                tree[os.path.relpath(path, folder)] = handle.read()
    return tree


def run_cli(machine, *args, stdin=None, env_extra=None, input_text=None, input_bytes=None):
    """bin/mail in a subprocess as one machine. stdin, or input_bytes (its alias, which StdinNotUtf8 passes), when given,
    is bytes piped to the CLI unchanged, and the result's stdout and stderr are then decoded as UTF-8 with replace, so
    a case reads the bytes the CLI wrote.
    input_text goes to the child's stdin, encoded as UTF-8 (the encoding argument below). env_extra overrides the
    machine's env for this run only."""
    env = dict(machine.env, **(env_extra or {}))
    if stdin is None:
        stdin = input_bytes
    if stdin is not None:
        raw = subprocess.run([sys.executable, MAIL_CLI, *args], env=env, cwd=machine.checkout, input=stdin,
                             capture_output=True, timeout=60)
        return subprocess.CompletedProcess(raw.args, raw.returncode, raw.stdout.decode("utf-8", "replace"),
                                           raw.stderr.decode("utf-8", "replace"))
    return subprocess.run([sys.executable, MAIL_CLI, *args], env=env,
                          cwd=machine.checkout, input=input_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)


def combined(result):
    return (result.stdout or "") + (result.stderr or "")


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


def fake_installer(case, name, fail_until=None, hang_for=None):
    """The install stand-in of a cloud refresh: an executable that appends one `ran` line to its log on each run. With
    fail_until, it exits 3 with a stderr line until that file exists. With hang_for, it writes its pid to <script>.pid,
    sleeps hang_for seconds, then logs `done`: a run killed at its bound logs `ran` and never `done`. Returns (command
    path, log path). POSIX only, so a case that runs it skips on Windows with NT_NO_STUB."""
    script = os.path.join(case, name)
    log = os.path.join(case, name + ".log")
    lines = ["#!/bin/sh", "printf 'ran\\n' >> %s" % shlex.quote(log)]
    if hang_for is not None:
        lines += ["printf '%%s\\n' $$ > %s" % shlex.quote(script + ".pid"), "sleep %d" % hang_for,
                  "printf 'done\\n' >> %s" % shlex.quote(log)]
    if fail_until:
        lines.append("if [ ! -e %s ]; then echo 'fake install broke' >&2; exit 3; fi" % shlex.quote(fail_until))
    lines.append("exit 0")
    with open(script, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(script, 0o755)
    return script, log


def git_subcommand(argv):
    """The git subcommand in an argv, past the options git takes before it (-c NAME=VALUE, -C DIR, ...)."""
    rest = list(argv[1:])
    while rest and rest[0] in ("-c", "-C", "--git-dir", "--work-tree"):
        rest = rest[2:]
    return rest[0] if rest else None


def push_count(trace):
    """How many `git push` runs the trace2 event log of one send records."""
    count = 0
    for line in read_lines(trace):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        argv = event.get("argv") or []
        if event.get("event") == "start" and argv and program_name(argv) == "git" and git_subcommand(argv) == "push":
            count += 1
    return count


def add_git_config(env, key, value):
    """Append one git config pair to an env dict, after any pairs already there."""
    count = int(env.get("GIT_CONFIG_COUNT") or 0)
    env["GIT_CONFIG_KEY_%d" % count] = key
    env["GIT_CONFIG_VALUE_%d" % count] = value
    env["GIT_CONFIG_COUNT"] = str(count + 1)


def turn(machine, session_id=None):
    """One UserPromptSubmit payload. A local session has no env id, so its payload names it with session_id."""
    payload = {"session_id": machine.session if session_id is None else session_id, "cwd": machine.checkout,
               "hook_event_name": "UserPromptSubmit", "prompt": "continue"}
    with mock.patch.dict(os.environ, machine.env, clear=True):
        return turn_start_lines(payload, machine.env)


def listed_with(lines, mid):
    return [line for line in lines if mid in line]


def cli_module():
    """bin/mail loaded once per run as a module, so a case can patch its clock and its push in this process."""
    name = "mail_cli_under_test"
    if name not in sys.modules:
        loader = importlib.machinery.SourceFileLoader(name, MAIL_CLI)
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
        sys.modules[name] = module
        loader.exec_module(module)
    return sys.modules[name]


@contextlib.contextmanager
def in_folder(path):
    here = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(here)


def cli_in_process(machine, *args):
    """bin/mail's main as one machine: its env, its checkout as the cwd, and PC_HOST as the host. The CLI
    subprocess sees the real host, so a case that addresses a fixed host runs here."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, machine.env, clear=True), mock.patch("socket.gethostname", return_value=PC_HOST), \
            in_folder(machine.checkout), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_module().main(list(args))
    return code, out.getvalue(), err.getvalue()


class MailCase(unittest.TestCase):
    def setUp(self):
        # A short name keeps git's paths under the Windows path limit. The test id is in each failure
        # message, so the folder needs only a unique name. makedirs refuses a clash.
        digest = hashlib.sha256(self.id().encode("utf-8")).hexdigest()[:10]
        self.case = os.path.join(ROOT, digest)
        os.makedirs(self.case)
        self.counter = 0

    def tearDown(self):
        tracked_tree.rm_tree(self.case)

    def store(self, name="store"):
        return Store(self.case, name)

    def machine(self, name, store, session=None, push_to=None, trace=None, origin=None, stub=False,
                prompt_env=True, identity=None):
        return Machine(self.case, name, store.url, session, push_to=push_to, trace=trace, origin=origin,
                       stub=stub, prompt_env=prompt_env, identity=identity)

    def cloud_machine(self, store, name, session, script):
        """A cloud session's machine: CLAUDE_CODE_REMOTE true, a checkout whose origin is ORIGIN, and the install stand-in
        named by MAILBOX_REFRESH_COMMAND."""
        machine = self.machine(name, store, session=session, origin=ORIGIN)
        machine.env.update({"CLAUDE_CODE_REMOTE": "true", "MAILBOX_REFRESH_COMMAND": script})
        return machine

    def body(self, marker):
        self.counter += 1
        path = os.path.join(self.case, "body-%d.md" % self.counter)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("Body marker: %s\n" % marker)
        return path

    def send(self, machine, to, kind, marker, re_id=None):
        args = ["send", "--to", to, "--kind", kind, "--body-file", self.body(marker)]
        if re_id is not None:
            args += ["--re", re_id]
        return run_cli(machine, *args)

    def assert_send_is_honest(self, sent, store, to, before):
        """The send contract: exit 0 only when the pushed tip's tree holds mail/<to>/<id>.md, <id> from the
        'sent <id>' line, and no path in that tree holds a CR. Otherwise exit 1 with a 'not sent: ' line, and the
        mail ref stays at before (None for an empty store)."""
        if sent.returncode != 0:
            self.assertEqual(sent.returncode, 1, "a refused send exited %d, expected 1: %s"
                             % (sent.returncode, combined(sent)))
            self.assertIn("not sent: ", combined(sent), "a refused send printed no 'not sent: <reason>' line: %r"
                          % combined(sent))
            self.assertEqual(store.tip(), before, "a refused send moved the mail ref")
            return
        cr = [path for path in store.files(raw=True) if "\r" in path]
        self.assertEqual(cr, [], "a send that exited 0 pushed a path with a CR in it: %r" % cr)
        sent_lines = [line for line in sent.stdout.splitlines() if line.startswith("sent ")]
        self.assertTrue(sent_lines, "a send that exited 0 printed no 'sent <id>' line: %r" % combined(sent))
        path = "mail/%s/%s.md" % (to, sent_lines[0].split()[1])
        self.assertIn(path, store.files(raw=True), "a send that exited 0 has its message in no pushed tree: %s" % path)

    def assert_stub_intercepted(self, machine, call="update-index --index-info",
                                effect="no update was dropped or CRLF'd"):
        """The stand-in git ran the git call that its action names. Without this, a case whose stub never ran
        passes on the old code, because the real git builds the healthy tree."""
        self.assertTrue(os.path.exists(machine.stub_marker),
                        "the stand-in git never intercepted %s, so %s" % (call, effect))


class RoundTrip(MailCase):
    def test_send_lands_then_receiver_turn_start_lists_it_and_read_shows_body(self):
        store = self.store()
        self.assertEqual(store.files(), [], "control: the store should start with no mail")
        sender = self.machine("a", store, session="sess-a")
        receiver = self.machine("b", store, session="sess-b")
        sent = self.send(sender, "cloud/sess-b", "request", "round-trip-1")
        self.assertEqual(sent.returncode, 0, "mail send exited %d: %s" % (sent.returncode, combined(sent)))
        landed = store.files("mail/cloud/sess-b/")
        self.assertEqual(len(landed), 1, "one send should land one message file: %r" % landed)
        mid = message_id(landed[0])
        listed = listed_with(turn(receiver), mid)
        self.assertEqual(len(listed), 1, "the receiver's turn start does not list %s once: %r" % (mid, listed))
        self.assertIn("request", listed[0], "the turn-start line does not give the kind: %r" % listed[0])
        self.assertIn("sess-a", listed[0], "the turn-start line does not give the sender: %r" % listed[0])
        read = run_cli(receiver, "read", mid)
        self.assertEqual(read.returncode, 0, "mail read exited %d: %s" % (read.returncode, combined(read)))
        self.assertIn("round-trip-1", read.stdout, "mail read did not show the body: %r" % read.stdout)


class PushRace(MailCase):
    def test_two_senders_on_separate_caches_all_land_when_one_cache_is_stale(self):
        store = self.store()
        sender_b = self.machine("b", store, session="sess-b1")
        sender_a = self.machine("a", store, session="sess-a1")
        first = self.send(sender_b, "cloud/sess-r", "request", "push-first-from-b")
        self.assertEqual(first.returncode, 0, "the first send exited %d: %s" % (first.returncode, combined(first)))
        self.assertEqual(len(store.files("mail/cloud/sess-r/")), 1,
                         "control: one message should land before the race")
        second = self.send(sender_a, "cloud/sess-r", "request", "push-from-a")
        self.assertEqual(second.returncode, 0, "the sender on the other cache exited %d: %s"
                         % (second.returncode, combined(second)))
        third = self.send(sender_b, "cloud/sess-r", "request", "push-second-from-b-stale")
        self.assertEqual(third.returncode, 0, "the stale-cache send exited %d: %s"
                         % (third.returncode, combined(third)))
        landed = store.files("mail/cloud/sess-r/")
        self.assertEqual(len(landed), 3, "a send lost its message in the push race: %r" % landed)
        bodies = [store.read(path) for path in landed]
        for marker in ("push-first-from-b", "push-from-a", "push-second-from-b-stale"):
            self.assertTrue(any(marker in body for body in bodies),
                            "the message %s is not on the store" % marker)


class TakeRace(MailCase):
    def test_second_taker_on_stale_cache_is_refused_and_one_done_file_remains(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e51", "request", "cloud/sess-a", "Body marker: take-race\n")
        taker_b = self.machine("b", store, session="sess-b")
        taker_a = self.machine("a", store, session="sess-b")
        listed = listed_with(turn(taker_b), "0a1b2c3d4e51")
        self.assertEqual(len(listed), 1, "control: the first taker's turn start does not list the message: %r" % listed)
        won = run_cli(taker_a, "take", "0a1b2c3d4e51")
        self.assertEqual(won.returncode, 0, "the first take exited %d: %s" % (won.returncode, combined(won)))
        lost = run_cli(taker_b, "take", "0a1b2c3d4e51")
        self.assertNotEqual(lost.returncode, 0, "the second take exited 0 after the first one won: %r" % combined(lost))
        self.assertIn("taken by another", combined(lost), "the second take did not say taken by another: %r" % combined(lost))
        self.assertEqual(store.files("mail/cloud/sess-b/"), [], "the mail path is still there after the take")
        done = store.files("done/cloud/sess-b/")
        self.assertEqual(len(done), 1, "the take race left %d done files, expected one: %r" % (len(done), done))
        self.assertIn("Taken-by:", store.read(done[0]), "the done file has no Taken-by line")


class InformClose(MailCase):
    def test_take_alone_closes_an_inform_and_sends_nothing_back(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e52", "inform", "cloud/sess-a", "Body marker: inform-close\n")
        receiver = self.machine("b", store, session="sess-b")
        before = listed_with(turn(receiver), "0a1b2c3d4e52")
        self.assertEqual(len(before), 1, "control: the inform is not listed before the take: %r" % before)
        self.assertIn("inform", before[0], "the inform's turn-start line does not give its kind: %r" % before[0])
        taken = run_cli(receiver, "take", "0a1b2c3d4e52")
        self.assertEqual(taken.returncode, 0, "the take exited %d: %s" % (taken.returncode, combined(taken)))
        after = listed_with(turn(receiver), "0a1b2c3d4e52")
        self.assertEqual(after, [], "the inform is still listed after take: %r" % after)
        self.assertEqual(store.files("mail/cloud/sess-a/"), [], "a reply landed for the sender after an inform")
        self.assertEqual(len(store.files("done/cloud/sess-b/")), 1, "the take did not leave one done file")


class Offline(MailCase):
    def missing_repo(self):
        return Path(os.path.join(self.case, "missing.git")).as_uri()

    def test_unreachable_repo_turn_start_prints_mail_unknown_never_no_mail(self):
        receiver = Machine(self.case, "b", self.missing_repo(), session="sess-b")
        lines = turn(receiver)
        unknown = [line for line in lines if line.startswith(UNKNOWN)]
        self.assertTrue(unknown, "an unreachable repo printed no 'mail unknown:' line: %r" % lines)
        self.assertTrue(unknown[0][len(UNKNOWN):].strip(), "the 'mail unknown:' line gives no reason: %r" % unknown[0])
        self.assertFalse(any("no mail" in line.lower() for line in lines),
                         "an unreachable repo read as an empty mailbox: %r" % lines)

    def test_unreachable_repo_read_prints_mail_unknown_never_no_mail(self):
        receiver = Machine(self.case, "b", self.missing_repo(), session="sess-b")
        read = run_cli(receiver, "read")
        text = combined(read)
        self.assertIn(UNKNOWN, text, "mail read on an unreachable repo did not print 'mail unknown:': %r" % text)
        self.assertNotIn("no mail", text.lower(), "mail read on an unreachable repo read as empty: %r" % text)

    def test_healthy_empty_store_is_read_and_is_not_unknown(self):
        store = self.store()
        receiver = self.machine("b", store, session="sess-b")
        with Starts() as starts:
            lines = turn(receiver)
        self.assertGreaterEqual(len(starts.git_starts()), 1,
                                "control: the turn never read the remote: %d git starts" % len(starts.git_starts()))
        self.assertFalse([line for line in lines if line.startswith(UNKNOWN)],
                         "a healthy empty store printed 'mail unknown:': %r" % lines)
        self.assertEqual(lines, [], "a store with no mail ref printed a line: %r" % lines)


class Cost(MailCase):
    def test_unchanged_mailbox_starts_one_git_process_and_writes_no_file(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e53", "request", "cloud/sess-a", "Body marker: cost\n")
        receiver = self.machine("b", store, session="sess-b")
        with Starts() as moved:
            lines = turn(receiver)
        self.assertEqual(len(listed_with(lines, "0a1b2c3d4e53")), 1,
                         "control: the moved turn does not list the open message: %r" % lines)
        self.assertLessEqual(len(moved.git_starts()), 4,
                             "a moved turn started %d git processes, at most 4 allowed" % len(moved.git_starts()))
        before = snapshot(self.case)
        with Starts() as unchanged:
            lines = turn(receiver)
        after = snapshot(self.case)
        self.assertEqual(len(listed_with(lines, "0a1b2c3d4e53")), 1,
                         "control: the unchanged turn does not list the open message: %r" % lines)
        self.assertEqual(len(unchanged.argv), 1,
                         "an unchanged turn started %d processes, expected exactly 1" % len(unchanged.argv))
        self.assertEqual(len(unchanged.git_starts()), 1,
                         "the one process an unchanged turn starts is not git: %r" % unchanged.argv)
        added = sorted(path for path in after if path not in before)
        removed = sorted(path for path in before if path not in after)
        changed = sorted(path for path in before if path in after and before[path] != after[path])
        self.assertEqual([added, removed, changed], [[], [], []],
                         "an unchanged turn wrote files: added %r, removed %r, changed %r" % (added, removed, changed))


class NotSent(MailCase):
    def counting_hook(self, store, pushes, script_body):
        """Writes a pre-receive hook on the store. Each push appends one line to PUSHES first."""
        hook = os.path.join(store.path, "hooks", "pre-receive")
        with open(hook, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("#!/bin/sh\necho push >> '%s'\n%s" % (pushes.replace("\\", "/"), script_body))
        os.chmod(hook, 0o755)

    def test_refused_push_is_not_retried_and_prints_not_sent_with_reason(self):
        store = self.store()
        pushes = os.path.join(self.case, "pushes.txt")
        self.counting_hook(store, pushes, "echo 'refused by the test store' >&2\nexit 1\n")
        sender = self.machine("a", store, session="sess-a")
        sent = self.send(sender, "cloud/sess-b", "request", "refused-once")
        attempts = read_lines(pushes)
        self.assertTrue(attempts, "control: the send never reached the store: %r" % combined(sent))
        self.assertEqual(len(attempts), 1, "a refused push was retried: %d pushes, expected 1" % len(attempts))
        self.assertEqual(sent.returncode, 1, "a refused send exited %d, expected 1: %s"
                         % (sent.returncode, combined(sent)))
        notices = [line for line in combined(sent).splitlines() if line.startswith("not sent: ")]
        self.assertTrue(notices, "a refused send printed no 'not sent: <reason>' line: %r" % combined(sent))
        self.assertTrue(notices[0][len("not sent: "):].strip(), "the 'not sent:' line gives no reason: %r" % notices[0])
        self.assertIn("refused by the test store", notices[0],
                      "the 'not sent:' line does not hold the hook's stderr text: %r" % notices[0])
        self.assertEqual(store.files(), [], "a refused message landed on the store anyway")

    def test_non_fast_forward_on_every_try_makes_six_pushes_then_not_sent_exit_1(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e61", "request", "cloud/sess-x", "Body marker: base\n")
        base = store.tip()
        # The push goes to a second store whose tip the sender never fetched. The commit is built on the
        # fetched tip, so the client refuses each push as a non-fast-forward before it sends anything.
        ahead = self.store(name="ahead")
        ahead.seed("cloud/sess-b", "0a1b2c3d4e71", "request", "cloud/sess-y", "Body marker: ahead\n")
        ahead_tip = ahead.tip()
        trace = os.path.join(self.case, "trace2.jsonl")
        sender = self.machine("a", store, session="sess-a", push_to=ahead.url, trace=trace)
        sent = self.send(sender, "cloud/sess-b", "request", "non-ff-every-try")
        pushes = push_count(trace)
        self.assertTrue(pushes, "control: the send made no push at all: %r" % combined(sent))
        self.assertEqual(pushes, 6, "a non-fast-forward on every try made %d pushes, expected 6 "
                         "(1 try and 5 retries); the send said %r" % (pushes, combined(sent)))
        self.assertEqual(sent.returncode, 1, "a send refused on every try exited %d, expected 1: %s"
                         % (sent.returncode, combined(sent)))
        self.assertIn("not sent", combined(sent).lower(), "a refused send did not print 'not sent': %r" % combined(sent))
        self.assertEqual(store.tip(), base, "a push moved the store the sender fetched")
        self.assertEqual(ahead.tip(), ahead_tip, "a refused push landed on the store it was sent to")


class ReplyThenTake(MailCase):
    def test_request_stays_listed_after_its_reply_until_take(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e54", "request", "cloud/sess-a", "Body marker: request-reply\n")
        receiver = self.machine("b", store, session="sess-b")
        before = listed_with(turn(receiver), "0a1b2c3d4e54")
        self.assertEqual(len(before), 1, "control: the request is not listed before the reply: %r" % before)
        replied = self.send(receiver, "cloud/sess-a", "reply", "reply-marker", re_id="0a1b2c3d4e54")
        self.assertEqual(replied.returncode, 0, "the reply exited %d: %s" % (replied.returncode, combined(replied)))
        landed = store.files("mail/cloud/sess-a/")
        self.assertEqual(len(landed), 1, "control: the reply did not land for the sender: %r" % landed)
        self.assertIn("re 0a1b2c3d4e54", store.read(landed[0]), "the reply does not name the request it answers")
        still = listed_with(turn(receiver), "0a1b2c3d4e54")
        self.assertEqual(len(still), 1, "the request left the receiver's turn start on its reply, before take: %r" % still)
        taken = run_cli(receiver, "take", "0a1b2c3d4e54")
        self.assertEqual(taken.returncode, 0, "the take exited %d: %s" % (taken.returncode, combined(taken)))
        after = listed_with(turn(receiver), "0a1b2c3d4e54")
        self.assertEqual(after, [], "the request is still listed after take: %r" % after)


class CloudAddress(MailCase):
    def test_cloud_id_cse_maps_to_session_address_and_mail_to_it_is_listed(self):
        store = self.store()
        sender = self.machine("a", store, session="cse_SENDER")
        receiver = self.machine("b", store, session="cse_ABC")
        sent = self.send(sender, "cloud/session_ABC", "request", "cloud-address")
        self.assertEqual(sent.returncode, 0, "mail send exited %d: %s" % (sent.returncode, combined(sent)))
        landed = store.files("mail/cloud/session_ABC/")
        self.assertEqual(len(landed), 1, "control: one send should land one message at cloud/session_ABC: %r" % landed)
        listed = listed_with(turn(receiver), message_id(landed[0]))
        self.assertEqual(len(listed), 1, "the receiver with CLAUDE_CODE_REMOTE_SESSION_ID=cse_ABC does not list "
                         "mail to cloud/session_ABC: its own address is not cloud/session_ABC: %r" % listed)


class PcSessionScope(MailCase):
    def test_session_mail_reaches_only_its_session_and_repo_mail_reaches_both(self):
        store = self.store()
        box = self.machine("pc", store, origin=ORIGIN)
        store.seed(PC_BASE + "/S1", "0a1b2c3d4e91", "request", PC_BASE + "/S2", "Body marker: s1-only\n")
        store.seed(PC_BASE, "0a1b2c3d4e92", "inform", PC_BASE + "/S2", "Body marker: repo-wide\n")
        with mock.patch("socket.gethostname", return_value=PC_HOST):
            s1 = turn(box, "S1")
            s2 = turn(box, "S2")
        self.assertEqual(len(listed_with(s1, "0a1b2c3d4e91")), 1,
                         "control: session S1 does not list mail to its own address: %r" % s1)
        self.assertEqual(listed_with(s2, "0a1b2c3d4e91"), [],
                         "session S2 lists mail addressed to session S1: %r" % s2)
        self.assertEqual(len(listed_with(s1, "0a1b2c3d4e92")), 1,
                         "control: session S1 does not list repo-wide mail: %r" % s1)
        self.assertEqual(len(listed_with(s2, "0a1b2c3d4e92")), 1,
                         "session S2 does not list mail to the repo address: %r" % s2)


class PcCommands(MailCase):
    def seeded(self):
        store = self.store()
        box = self.machine("pc", store, origin=ORIGIN)
        store.seed(PC_BASE + "/S1", "0a1b2c3d4e93", "request", PC_BASE + "/S2", "Body marker: s1-commands\n")
        return store, box

    def test_turn_start_line_names_take_with_addr_for_session_mail(self):
        store, box = self.seeded()
        with mock.patch("socket.gethostname", return_value=PC_HOST):
            lines = listed_with(turn(box, "S1"), "0a1b2c3d4e93")
        self.assertEqual(len(lines), 1, "control: session S1 does not list its own mail: %r" % lines)
        command = "mail take --addr %s/S1 0a1b2c3d4e93" % PC_BASE
        self.assertIn(command, lines[0], "the turn-start line does not name the exact take command: %r" % lines[0])

    def test_cli_read_and_take_with_addr_reach_session_mail(self):
        store, box = self.seeded()
        addr = PC_BASE + "/S1"
        read = run_cli(box, "read", "--addr", addr, "0a1b2c3d4e93")
        self.assertEqual(read.returncode, 0, "mail read --addr exited %d: %s" % (read.returncode, combined(read)))
        self.assertIn("Body marker: s1-commands", read.stdout, "mail read --addr did not show the body: %r" % read.stdout)
        taken = run_cli(box, "take", "--addr", addr, "0a1b2c3d4e93")
        self.assertEqual(taken.returncode, 0, "mail take --addr exited %d: %s" % (taken.returncode, combined(taken)))
        self.assertEqual(len(store.files("done/" + addr + "/")), 1,
                         "mail take --addr left no done file for session S1: %r" % store.files("done/"))
        self.assertEqual(store.files("mail/" + addr + "/"), [], "mail take --addr left the message open")


class TurnBound(MailCase):
    def seeded_receiver(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e71", "request", "cloud/sess-a", "Body marker: bound\n")
        return self.machine("b", store, session="sess-b")

    def test_moved_turn_git_bounds_sum_to_ten_seconds_or_less(self):
        receiver = self.seeded_receiver()
        with Starts() as moved:
            lines = turn(receiver)
        self.assertTrue(listed_with(lines, "0a1b2c3d4e71"), "control: the moved turn does not list the message: %r" % lines)
        self.assertTrue(moved.git_starts(), "control: the moved turn started no git")
        self.assertNotIn(None, moved.git_bounds(), "a git start in the turn has no timeout: %r" % moved.git_bounds())
        total = sum(moved.git_bounds())
        self.assertLessEqual(total, 10, "the moved turn's git timeouts %r sum to %s s, over the 10 s bound"
                             % (moved.git_bounds(), total))

    def test_hung_fetch_prints_mail_unknown_timeout(self):
        receiver = self.seeded_receiver()
        with Starts(expire=("fetch",)):
            lines = turn(receiver)
        self.assertIn(UNKNOWN + "timeout", lines, "a hung fetch did not print 'mail unknown: timeout': %r" % lines)
        self.assertFalse(any("no mail" in line.lower() for line in lines),
                         "a hung fetch read as an empty mailbox: %r" % lines)


class LocalTimeMailLines(MailCase):
    def hook_stdout(self, **patch_kwargs):
        import local_time  # hooks/local_time.py: the caller of mail.turn_start_lines
        import mail as mail_module
        raw = json.dumps({"session_id": "sess-b", "cwd": self.case}).encode("utf-8")
        out, escaped = io.StringIO(), None
        with mock.patch.object(mail_module, "turn_start_lines", **patch_kwargs), contextlib.redirect_stdout(out):
            try:
                local_time.mail_lines(raw)
            except Exception as error:  # reported by the assert below, so the cause reads as the assert
                escaped = error
        return out.getvalue().splitlines(), escaped

    def test_control_prints_the_lines_the_mail_module_returns(self):
        lines, escaped = self.hook_stdout(return_value=["mail: control-line"])
        self.assertIsNone(escaped, "control: mail_lines raised on a healthy mail module: %r" % escaped)
        self.assertEqual(lines, ["mail: control-line"], "control: mail_lines did not print the module's lines")

    def test_mail_module_error_prints_mail_unknown_line_on_stdout(self):
        lines, escaped = self.hook_stdout(side_effect=RuntimeError("boom"))
        self.assertIsNone(escaped, "mail_lines let the mail module's error out instead of printing a line: %r" % escaped)
        self.assertIn(UNKNOWN + "boom", lines, "stdout has no 'mail unknown: <reason>' line: %r" % lines)


class ReadShowFails(MailCase):
    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_read_with_git_show_failing_prints_mail_unknown_not_no_open_message(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e81", "request", "cloud/sess-a", "Body marker: show\n")
        reader = self.machine("b", store, session="sess-b", stub=True)
        ok = run_cli(reader, "read", "0a1b2c3d4e81")
        self.assertEqual(ok.returncode, 0, "control: a healthy mail read exited %d: %s" % (ok.returncode, combined(ok)))
        self.assertIn("Body marker: show", ok.stdout, "control: a healthy mail read did not show the body")
        absent = run_cli(reader, "read", "0a1b2c3d4e82")
        self.assertIn("no open message 0a1b2c3d4e82", combined(absent), "control: an absent id did not say no open message")
        reader.stub_actions({"show": {"kind": "fail", "stderr": "fatal: bad object 0a1b2c3d4e81"}})
        broken = run_cli(reader, "read", "0a1b2c3d4e81")
        self.assertIn(UNKNOWN, combined(broken), "mail read with git show failing did not print 'mail unknown:': %r"
                      % combined(broken))
        self.assertNotIn("no open message", combined(broken), "mail read with git show failing read as no open message: %r"
                         % combined(broken))


class PushRefusedRetry(MailCase):
    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_push_refused_by_an_interloper_lands_on_try_two(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e95", "request", "cloud/sess-x", "Body marker: base\n")
        interloper = self.machine("c", store, session="sess-c")
        trace = os.path.join(self.case, "trace2.jsonl")
        sender = self.machine("b", store, session="sess-b", trace=trace, stub=True)
        record = os.path.join(self.case, "interloper.json")
        sender.stub_actions({"push": {
            "kind": "before", "once": os.path.join(self.case, "once.marker"), "record": record, "env": interloper.env,
            "argv": [sys.executable, MAIL_CLI, "send", "--to", "cloud/sess-b", "--kind", "inform",
                     "--body-file", self.body("interloper")]}})
        sent = self.send(sender, "cloud/sess-b", "request", "push-race-sender")
        with open(record, encoding="utf-8") as handle:
            landed_first = json.load(handle)
        self.assertEqual(landed_first["code"], 0, "control: the interloper's send did not land: %r" % landed_first["out"])
        self.assertEqual(sent.returncode, 0, "the send that lost the push race exited %d: %s"
                         % (sent.returncode, combined(sent)))
        self.assertEqual(push_count(trace), 2, "the send made %d pushes, expected 2 (one refused, one landed)"
                         % push_count(trace))
        landed = [path for path in store.files("mail/cloud/sess-b/") if "push-race-sender" in store.read(path)]
        self.assertEqual(len(landed), 1, "the send's message did not land once on the store: %r" % landed)
        header = store.read(landed[0]).splitlines()[0]
        self.assertEqual(header.split()[-2:], ["try", "2"], "the message did not land on try 2: %r" % header)


class TakeBothFromOneTip(MailCase):
    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_two_takers_from_one_tip_one_takes_and_the_other_is_taken_by_another(self):
        store = self.store()
        mid = "0a1b2c3d4e96"
        store.seed("cloud/sess-b", mid, "request", "cloud/sess-a", "Body marker: both-takers\n")
        first = self.machine("a", store, session="sess-b", identity=OTHER_IDENTITY)
        second = self.machine("b", store, session="sess-b", stub=True)
        record = os.path.join(self.case, "first-taker.json")
        second.stub_actions({"push": {
            "kind": "before", "once": os.path.join(self.case, "once.marker"), "record": record, "env": first.env,
            "argv": [sys.executable, MAIL_CLI, "take", mid]}})
        lost = run_cli(second, "take", mid)
        with open(record, encoding="utf-8") as handle:
            won = json.load(handle)
        self.assertEqual(won["code"], 0, "control: the first taker did not take: %r" % won["out"])
        self.assertIn("taken %s" % mid, won["out"], "control: the first taker did not print taken: %r" % won["out"])
        self.assertNotEqual(lost.returncode, 0, "the second taker exited 0 after the first one took: %r" % combined(lost))
        self.assertIn("taken by another", combined(lost), "the second taker did not say taken by another: %r"
                      % combined(lost))
        self.assertNotIn("taken %s" % mid, combined(lost), "both takers printed taken: %r" % combined(lost))
        self.assertEqual(len(store.files("done/cloud/sess-b/")), 1, "the take race left %r done files, expected one"
                         % store.files("done/cloud/sess-b/"))


class PromptEnv(MailCase):
    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_every_git_start_sets_no_prompt_and_no_credential_prompt(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e97", "request", "cloud/sess-a", "Body marker: prompt\n")
        log = os.path.join(self.case, "git-starts.jsonl")
        receiver = self.machine("b", store, session="sess-b", stub=True, prompt_env=False)
        receiver.stub_actions({}, log=log)
        turn(receiver)
        sent = self.send(receiver, "cloud/sess-a", "reply", "prompt-reply", re_id="0a1b2c3d4e97")
        self.assertEqual(sent.returncode, 0, "control: the reply exited %d: %s" % (sent.returncode, combined(sent)))
        starts = [json.loads(line) for line in read_lines(log)]
        self.assertTrue(starts, "control: no git start was logged")
        self.assertEqual([s["sub"] for s in starts if s["env"].get("GIT_TERMINAL_PROMPT") != "0"], [],
                         "git starts ran without GIT_TERMINAL_PROMPT=0")
        self.assertEqual([s["sub"] for s in starts if s["env"].get("GCM_INTERACTIVE") != "never"], [],
                         "git starts ran without GCM_INTERACTIVE=never")


class LocalSessionRead(MailCase):
    def test_read_without_addr_lists_the_local_sessions_own_folder(self):
        store = self.store()
        box = self.machine("pc", store, origin=ORIGIN)
        box.env["CLAUDE_CODE_SESSION_ID"] = "sessA"
        mid = "0a1b2c3d4e98"
        store.seed(PC_BASE + "/sessA", mid, "request", PC_BASE + "/sessB", "Body marker: local-read\n")
        self.assertEqual(len(store.files("mail/" + PC_BASE + "/sessA/")), 1,
                         "control: the message did not land in the session folder")
        named = cli_in_process(box, "read", "--addr", PC_BASE + "/sessA")
        self.assertIn(mid, named[1], "control: mail read --addr does not list the session folder's message: %r"
                      % named[1])
        code, out, err = cli_in_process(box, "read")
        self.assertEqual(code, 0, "mail read with no --addr exited %d: %r" % (code, err))
        self.assertIn(mid, out, "mail read with no --addr did not list the open message in the local session's "
                      "own folder: %r" % out)


class TakeSameSecond(MailCase):
    def test_two_caches_taking_one_message_in_one_second_print_taken_once(self):
        store = self.store()
        mid = "0a1b2c3d4e61"
        store.seed("cloud/sess-b", mid, "request", "cloud/sess-a", "Body marker: same-second\n")
        first = self.machine("t1", store, session="sess-b")
        second = self.machine("t2", store, session="sess-b")
        first.env.update(SAME_SECOND)
        second.env.update(SAME_SECOND)
        self.assertEqual(len(store.files("mail/cloud/sess-b/")), 1, "control: the message did not land")
        cli = cli_module()
        results, interleaved = {}, []
        real_push = cli.mail.push

        def take_as(name, machine):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.take(machine.env, ["cloud/sess-b"], mid)
            results[name] = (code, out.getvalue(), err.getvalue())

        def push_after_the_second_take(env, commit):
            # The second taker syncs and pushes between the first taker's build and its push, so both build on one tip.
            if env is first.env and not interleaved:
                interleaved.append(True)
                take_as("second", second)
            return real_push(env, commit)

        with mock.patch.object(cli, "stamp", return_value=PINNED_STAMP), \
                mock.patch.object(cli.mail, "push", new=push_after_the_second_take):
            take_as("first", first)
        self.assertTrue(interleaved, "control: the second taker never ran inside the first taker's take: %r" % results)
        printed = [name for name in ("first", "second") if "taken %s" % mid in results[name][1].splitlines()]
        self.assertEqual(len(printed), 1, "two takers of one message in one second both printed taken: %r" % results)
        self.assertEqual(len(store.files("done/cloud/sess-b/")), 1, "the take race left %r done files, expected one"
                         % store.files("done/cloud/sess-b/"))


class SshBatchDefault(MailCase):
    def git_ssh_command(self, extra=None):
        """The GIT_SSH_COMMAND that one git start of the hook carries, read from the env it is started with."""
        env = fixture_env(self.case, extra)
        done = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(MAIL_MODULE._nowindow, "run", return_value=done) as run:
            MAIL_MODULE.git(["ls-remote", self.case, REFUSED], env)
        return run.call_args.kwargs["env"].get("GIT_SSH_COMMAND")

    def test_default_ssh_command_runs_in_batch_mode(self):
        command = self.git_ssh_command()
        self.assertIn("BatchMode=yes", command or "", "the default ssh command is not batch mode: %r" % command)

    def test_default_ssh_command_bounds_the_connect_time(self):
        command = self.git_ssh_command()
        self.assertIn("ConnectTimeout=3", command or "", "the default ssh command has no 3 s connect bound: %r"
                      % command)

    def test_caller_set_ssh_command_is_kept(self):
        command = self.git_ssh_command({"GIT_SSH_COMMAND": "my-ssh -i key"})
        self.assertEqual(command, "my-ssh -i key", "git's ssh command was replaced although the caller set one: %r"
                         % command)


class MacNotHeld(MailCase):
    """No platform is held by default (step mail-mac-unhold)."""

    def test_no_platform_is_held(self):
        self.assertEqual(MAIL_MODULE.HELD_PLATFORMS, (), "a platform is held by default: %r" % (MAIL_MODULE.HELD_PLATFORMS,))

    def test_mac_turn_start_lists_the_message_with_no_hold_off(self):
        store = self.store()
        mid = "0a1b2c3d4ebb"
        store.seed("cloud/sess-b", mid, "request", "cloud/sess-a", "Body marker: mac-open\n")
        reader = self.machine("b", store, session="sess-b")
        reader.env.pop("MAILBOX_HOLD_OFF")
        with mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
            lines = turn(reader)
        self.assertEqual(len(listed_with(lines, mid)), 1, "a Mac turn start is still held: %r" % lines)


class MacHold(MailCase):
    """Step mail-mac-unhold: the hold mechanism for a platform in HELD_PLATFORMS. The cases below patch the tuple to
    ("darwin",) and prove the turn-start line and the `mail` command are both held there, and that MAILBOX_HOLD_OFF=1 lifts
    the hold. The default tuple is empty; `MacNotHeld` pins that."""

    def setUp(self):
        super().setUp()
        for module in (MAIL_MODULE, cli_module().mail):  # bin/mail holds its own copy of hooks/mail.py
            patch = mock.patch.object(module, "HELD_PLATFORMS", ("darwin",))
            patch.start()
            self.addCleanup(patch.stop)

    def seeded_reader(self, hold_off=False):
        store = self.store()
        mid = "0a1b2c3d4eaa"
        store.seed("cloud/sess-b", mid, "request", "cloud/sess-a", "Body marker: mac-hold\n")
        reader = self.machine("b", store, session="sess-b")
        if hold_off:
            reader.env["MAILBOX_HOLD_OFF"] = "1"
        else:
            reader.env.pop("MAILBOX_HOLD_OFF")
        return mid, store, reader

    def test_linux_turn_start_lists_the_message(self):
        mid, _, reader = self.seeded_reader()
        with mock.patch.object(MAIL_MODULE.sys, "platform", "linux"):
            lines = turn(reader)
        self.assertEqual(len(listed_with(lines, mid)), 1, "control: a Linux turn does not list the message: %r" % lines)

    def test_mac_turn_start_prints_nothing_for_an_open_message(self):
        mid, _, reader = self.seeded_reader()
        with mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
            lines = turn(reader)
        self.assertEqual(lines, [], "a Mac turn start read the mailbox before its check passed: %r" % lines)

    def test_mac_turn_start_lists_the_message_with_the_hold_off(self):
        mid, _, reader = self.seeded_reader(hold_off=True)
        with mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
            lines = turn(reader)
        self.assertEqual(len(listed_with(lines, mid)), 1, "MAILBOX_HOLD_OFF=1 on a Mac did not lift the hold: %r" % lines)

    def test_mac_send_is_refused_and_stores_nothing(self):
        mid, store, reader = self.seeded_reader()
        tip = store.tip()
        with mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
            code, out, err = cli_in_process(reader, "send", "--to", "cloud/sess-a", "--kind", "inform",
                                            "--body-file", self.body("held-send"))
        self.assertEqual(code, 2, "a held Mac send exited %r, not 2: %r %r" % (code, out, err))
        self.assertIn("held", err, "the refusal does not say the mailbox is held: %r" % err)
        self.assertNotIn("sent", out, "a held Mac send printed sent: %r" % out)
        self.assertEqual(store.tip(), tip, "a held Mac send moved the mail ref")

    def test_mac_read_is_refused(self):
        mid, _, reader = self.seeded_reader()
        with mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
            code, out, err = cli_in_process(reader, "read", "--addr", "cloud/sess-b")
        self.assertEqual(code, 2, "a held Mac read exited %r, not 2: %r %r" % (code, out, err))
        self.assertNotIn(mid, out, "a held Mac read listed the message: %r" % out)
        self.assertIn("held", err, "the held read printed no refusal: %r" % err)
        self.assertNotIn("MAILBOX_HOLD_OFF", err, "the held refusal names the variable that lifts the hold: %r" % err)

    def test_only_one_lifts_the_hold(self):
        for value in ("0", "false", ""):
            with self.subTest(value=value), mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
                self.assertTrue(MAIL_MODULE.held({"MAILBOX_HOLD_OFF": value}), "MAILBOX_HOLD_OFF=%r lifted the hold" % value)
        with mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
            self.assertFalse(MAIL_MODULE.held({"MAILBOX_HOLD_OFF": "1"}), "MAILBOX_HOLD_OFF=1 did not lift the hold")

    def test_mac_send_runs_with_the_hold_off(self):
        mid, store, reader = self.seeded_reader(hold_off=True)
        tip = store.tip()
        with mock.patch.object(MAIL_MODULE.sys, "platform", "darwin"):
            code, out, err = cli_in_process(reader, "send", "--to", "cloud/sess-a", "--kind", "inform",
                                            "--body-file", self.body("open-send"))
        self.assertEqual(code, 0, "the Mac check send exited %r with the hold off: %r %r" % (code, out, err))
        self.assertNotEqual(store.tip(), tip, "the Mac check send stored nothing")


class AgeUnknown(MailCase):
    def healthy_line(self, store, mid):
        """The turn-start line of a machine whose git log works, so each failing case has a line to compare."""
        lines = listed_with(turn(self.machine("c", store, session="sess-b")), mid)
        self.assertEqual(len(lines), 1, "control: a healthy turn does not list the message: %r" % lines)
        self.assertNotIn("age unknown", lines[0], "control: a healthy turn says age unknown: %r" % lines[0])
        return lines[0]

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_failing_git_log_still_lists_the_message_as_age_unknown(self):
        store = self.store()
        mid = "0a1b2c3d4e99"
        store.seed("cloud/sess-b", mid, "request", "cloud/sess-a", "Body marker: age-fail\n")
        self.healthy_line(store, mid)
        reader = self.machine("b", store, session="sess-b", stub=True)
        reader.stub_actions({"log": {"kind": "fail", "stderr": "fatal: bad revision"}})
        lines = turn(reader)
        listed = listed_with(lines, mid)
        self.assertEqual(len(listed), 1, "a failing git log hid the message from the turn start: %r" % lines)
        self.assertIn("age unknown", listed[0], "a failing git log did not print age unknown: %r" % listed[0])

    def test_timed_out_git_log_still_lists_the_message_as_age_unknown(self):
        store = self.store()
        mid = "0a1b2c3d4e9a"
        store.seed("cloud/sess-b", mid, "request", "cloud/sess-a", "Body marker: age-timeout\n")
        self.healthy_line(store, mid)
        reader = self.machine("b", store, session="sess-b")
        with Starts(expire=("log",)):
            lines = turn(reader)
        listed = listed_with(lines, mid)
        self.assertEqual(len(listed), 1, "a timed-out git log hid the message from the turn start: %r" % lines)
        self.assertIn("age unknown", listed[0], "a timed-out git log did not print age unknown: %r" % listed[0])


class IndexUpdateDropped(MailCase):
    """A git helper drops the update-index stdin and does nothing, exiting 0. The tree write-tree then builds is the
    parent's, so the send must not report success. Stub action: drop, on update-index."""

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_dropped_index_update_on_a_seeded_store_is_not_sent_and_keeps_the_tip(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e51", "request", "cloud/sess-x", "Body marker: base\n")
        sender = self.machine("a", store, session="sess-a", stub=True)
        control = self.send(sender, "cloud/sess-b", "request", "dropped-control")
        self.assertEqual(control.returncode, 0, "control: a healthy send exited %d: %s"
                         % (control.returncode, combined(control)))
        before = store.tip()
        sender.stub_actions({"update-index": {"kind": "drop"}})
        sent = self.send(sender, "cloud/sess-b", "request", "dropped-send")
        self.assert_stub_intercepted(sender)
        self.assert_send_is_honest(sent, store, "cloud/sess-b", before)

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_dropped_index_update_on_an_empty_store_is_not_sent_and_creates_no_ref(self):
        store = self.store()
        self.assertIsNone(store.tip(), "control: the store should start with no mail ref")
        sender = self.machine("a", store, session="sess-a", stub=True)
        sender.stub_actions({"update-index": {"kind": "drop"}})
        sent = self.send(sender, "cloud/sess-b", "request", "dropped-empty")
        self.assert_stub_intercepted(sender)
        self.assert_send_is_honest(sent, store, "cloud/sess-b", None)


class CrlfIndexLines(MailCase):
    """update-index reads each index line with a CR before its LF, as a text-mode pipe on Windows writes it. Git keeps
    that CR in the path. Stub action: crlf, on update-index --index-info."""

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_crlf_index_lines_never_push_a_path_with_a_cr(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e61", "request", "cloud/sess-x", "Body marker: base\n")
        sender = self.machine("a", store, session="sess-a", stub=True)
        control = self.send(sender, "cloud/sess-b", "request", "crlf-control")
        self.assertEqual(control.returncode, 0, "control: a healthy send exited %d: %s"
                         % (control.returncode, combined(control)))
        before = store.tip()
        sender.stub_actions({"update-index": {"kind": "crlf"}})
        sent = self.send(sender, "cloud/sess-b", "request", "crlf-send")
        self.assert_stub_intercepted(sender)
        self.assert_send_is_honest(sent, store, "cloud/sess-b", before)


class ReadBackFromTip(MailCase):
    """A good send, read back from the pushed tip: mail/<to>/<id>.md holds the body file's bytes, and no path or
    content in the tip's tree holds a CR. Linux writes LF, so this case holds on any correct send; it guards the
    read-back, and the CR defects are simulated in CrlfIndexLines and IndexUpdateDropped."""

    def send_and_read_back(self, store, sender, marker):
        body_path = self.body(marker)
        sent = run_cli(sender, "send", "--to", "cloud/sess-b", "--kind", "request", "--body-file", body_path)
        self.assertEqual(sent.returncode, 0, "a good send exited %d: %s" % (sent.returncode, combined(sent)))
        self.assertTrue(sent.stdout.startswith("sent "), "a good send printed no 'sent <id>' line: %r" % combined(sent))
        path = "mail/cloud/sess-b/%s.md" % sent.stdout.split()[1]
        tree = store.files(raw=True)
        self.assertIn(path, tree, "the pushed tip's tree holds no %s" % path)
        cr = [entry for entry in tree if "\r" in entry]
        self.assertEqual(cr, [], "the pushed tip's tree holds a path with a CR in it: %r" % cr)
        with open(body_path, "rb") as handle:
            body = handle.read()
        content = store.read(path, raw=True)
        self.assertNotIn(b"\r", content, "the pushed message holds a CR: %r" % content)
        self.assertIn(b"\n\n", content, "the pushed message has no body after its header: %r" % content)
        self.assertEqual(content.split(b"\n\n", 1)[1], body,
                         "the pushed body is not the body file's bytes: %r" % content)

    def test_good_send_into_an_empty_store_reads_back_its_body_bytes(self):
        store = self.store()
        sender = self.machine("a", store, session="sess-a")
        self.send_and_read_back(store, sender, "read-back-empty")

    def test_good_send_into_a_store_with_mail_reads_back_its_body_bytes(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e71", "request", "cloud/sess-x", "Body marker: base\n")
        sender = self.machine("a", store, session="sess-a")
        self.send_and_read_back(store, sender, "read-back-full")


class TakeRemovalDropped(MailCase):
    """A take whose index update keeps the add line and drops the removal line. The take read-back must see the message
    still on the tip, so the take prints no "taken" line and fails. Stub action: drop-removal, on update-index."""

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_take_whose_removal_line_is_dropped_prints_no_taken_and_keeps_the_message_open(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e83", "request", "cloud/sess-x", "Body marker: take-control\n")
        store.seed("cloud/sess-b", "0a1b2c3d4e84", "request", "cloud/sess-x", "Body marker: take-dropped\n")
        taker = self.machine("b", store, session="sess-b", stub=True)
        control = run_cli(taker, "take", "0a1b2c3d4e83")
        self.assertEqual(control.returncode, 0, "control: a healthy take exited %d: %s"
                         % (control.returncode, combined(control)))
        self.assertIn("taken 0a1b2c3d4e83", control.stdout.splitlines(),
                      "control: a healthy take printed no taken line: %r" % control.stdout)
        before = store.tip()
        taker.stub_actions({"update-index": {"kind": "drop-removal"}})
        taken = run_cli(taker, "take", "0a1b2c3d4e84")
        self.assert_stub_intercepted(taker)
        printed = [line for line in taken.stdout.splitlines() if line.startswith("taken ")]
        self.assertEqual(printed, [], "a take whose removal line was dropped printed taken, "
                         "with the old file still open: %r" % taken.stdout)
        self.assertEqual(taken.returncode, 1, "a take whose removal line was dropped exited %d, expected 1: %s"
                         % (taken.returncode, combined(taken)))
        self.assertIn("message file missing from the commit", taken.stderr,
                      "a take whose removal line was dropped failed for another cause: %r" % taken.stderr)
        self.assertEqual(store.tip(), before, "a take whose removal line was dropped moved the mail ref")
        self.assertIn("mail/cloud/sess-b/0a1b2c3d4e84.md", store.files("mail/cloud/sess-b/"),
                      "the message left its open folder although the take did not finish")
        self.assertEqual(store.files("done/cloud/sess-b/0a1b2c3d4e84"), [],
                         "a take that did not finish left a done file behind")


class StdinAsciiBody(MailCase):
    """An ASCII body piped on stdin is pushed as its own bytes. A body that is not UTF-8 is StdinNotUtf8's case."""

    def send_stdin(self, machine, body):
        return run_cli(machine, "send", "--to", "cloud/sess-b", "--kind", "request", "--body-file", "-", stdin=body)

    def test_control_ascii_body_on_stdin_sends_and_pushes_its_bytes(self):
        store = self.store()
        sender = self.machine("a", store, session="sess-a")
        body = b"Body marker: stdin-control\n"
        sent = self.send_stdin(sender, body)
        self.assertEqual(sent.returncode, 0, "control: an ASCII body on stdin exited %d: %s"
                         % (sent.returncode, combined(sent)))
        self.assertTrue(sent.stdout.startswith("sent "), "control: an ASCII body on stdin printed no sent line: %r"
                        % sent.stdout)
        path = "mail/cloud/sess-b/%s.md" % sent.stdout.split()[1]
        self.assertIn(path, store.files(), "control: the pushed tip holds no %s" % path)
        self.assertTrue(store.read(path, raw=True).endswith(body), "control: the pushed message lost its body bytes")


class IgnoredPathStderr(MailCase):
    """Git prints "Ignoring path" on stderr and still exits 0. The entries land in this stand-in, so only the stderr
    shows the skip. A git call that reports an ignored path is an error, and the send must say not sent."""

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_send_whose_git_reports_an_ignored_path_is_not_sent(self):
        store = self.store()
        sender = self.machine("a", store, session="sess-a", stub=True)
        control = self.send(sender, "cloud/sess-b", "request", "control")
        self.assertEqual(control.returncode, 0, "control: a healthy send exited %d: %s"
                         % (control.returncode, combined(control)))
        self.assertEqual(len(store.files("mail/cloud/sess-b/")), 1, "control: a healthy send did not land its message")
        sender.stub_actions({"update-index": {"kind": "warn",
                                              "stderr": "Ignoring path mail/cloud/sess-b/ignored.md\n"}})
        landed_before = len(store.files("mail/cloud/sess-b/"))
        sent = self.send(sender, "cloud/sess-b", "request", "warned")
        self.assert_stub_intercepted(sender)
        self.assertNotEqual(sent.returncode, 0, "git printed 'Ignoring path' and the send exited 0: %r" % combined(sent))
        self.assertIn("not sent: ", sent.stderr, "a failed send printed no 'not sent:' line: %r" % sent.stderr)
        self.assertEqual(len(store.files("mail/cloud/sess-b/")), landed_before,
                         "the send landed a message after git printed 'Ignoring path'")

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_benign_stderr_line_from_git_still_lets_the_send_print_sent(self):
        store = self.store()
        sender = self.machine("a", store, session="sess-a", stub=True)
        sender.stub_actions({"update-index": {"kind": "warn",
                                              "stderr": "hint: a benign git note, not an ignored path\n"}})
        sent = self.send(sender, "cloud/sess-b", "request", "benign")
        self.assert_stub_intercepted(sender)
        self.assertEqual(sent.returncode, 0, "git printed a benign stderr line and the send exited %d: %s"
                         % (sent.returncode, combined(sent)))
        self.assert_send_is_honest(sent, store, "cloud/sess-b", None)


class CrlfBlobHashed(MailCase):
    """hash-object reads its stdin with a CR before each LF, as a text-mode pipe on Windows writes it. The blob
    it stores is not the blob of the text, so the tree holds other bytes than the body the send was given. The send
    refuses it, and the mail ref does not move. Stub action: crlf-stdin, on hash-object --stdin."""

    def assert_refused(self, machine, store, before, sent):
        self.assert_stub_intercepted(machine, "hash-object --stdin", "no blob was made from CRLF stdin")
        self.assertEqual(sent.returncode, 1, "a send whose blob came from CRLF stdin exited %d, expected 1: %s"
                         % (sent.returncode, combined(sent)))
        self.assertIn("not sent: message file missing from the commit", sent.stderr,
                      "a send whose blob came from CRLF stdin was refused for another cause: %r" % sent.stderr)
        self.assertEqual(store.tip(), before, "a send whose blob came from CRLF stdin moved the mail ref")

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_blob_from_crlf_stdin_is_not_sent_on_a_seeded_store_and_keeps_the_tip(self):
        store = self.store()
        store.seed("cloud/sess-b", "0a1b2c3d4e91", "request", "cloud/sess-x", "Body marker: base\n")
        sender = self.machine("a", store, session="sess-a", stub=True)
        control = self.send(sender, "cloud/sess-b", "request", "crlf-blob-control")
        self.assertEqual(control.returncode, 0, "control: a healthy send exited %d: %s"
                         % (control.returncode, combined(control)))
        before = store.tip()
        sender.stub_actions({"hash-object": {"kind": "crlf-stdin"}})
        sent = self.send(sender, "cloud/sess-b", "request", "crlf-blob-send")
        self.assert_refused(sender, store, before, sent)

    @unittest.skipIf(os.name == "nt", NT_NO_STUB)
    def test_blob_from_crlf_stdin_is_not_sent_on_an_empty_store_and_creates_no_ref(self):
        store = self.store()
        self.assertIsNone(store.tip(), "control: the store should start with no mail ref")
        sender = self.machine("a", store, session="sess-a", stub=True)
        sender.stub_actions({"hash-object": {"kind": "crlf-stdin"}})
        sent = self.send(sender, "cloud/sess-b", "request", "crlf-blob-empty")
        self.assert_refused(sender, store, None, sent)


MARKER = "ascii-ok: flow → kept"  # U+2192 has no cp1252 code point
ARROW = "→"
BODY = "Body marker: %s\n" % MARKER  # the text MailCase.body writes for this marker


class Cp1252Pipe(MailCase):
    """Windows runs bin/mail on a cp1252 pipe (PYTHONIOENCODING=cp1252). A body with an arrow must be stored as
    UTF-8 intact, and `mail read` must return it unchanged."""

    def pair(self):
        store = self.store()
        sender = self.machine("a", store, session="sess-a")
        receiver = self.machine("b", store, session="sess-b")
        for machine in (sender, receiver):
            machine.env["PYTHONIOENCODING"] = "cp1252"
            self.assert_cp1252_pipe(machine)
        return store, sender, receiver

    def assert_cp1252_pipe(self, machine):
        """Scope before subject: the child runs on a cp1252 stdin, stdout and stderr, so the cases test that pipe."""
        probe = subprocess.run([sys.executable, "-c",
                                "import sys; print(sys.stdin.encoding, sys.stdout.encoding, sys.stderr.encoding)"],
                               env=machine.env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(probe.stdout.split(), ["cp1252", "cp1252", "cp1252"],
                         "control: the child does not run on a cp1252 pipe: %r" % probe.stdout)

    def test_stdin_body_with_arrow_is_stored_intact_and_reads_back_unchanged(self):
        store, sender, receiver = self.pair()
        sent = run_cli(sender, "send", "--to", "cloud/sess-b", "--kind", "request", "--body-file", "-",
                       input_text=BODY)
        self.assertEqual(sent.returncode, 0,
                         "send from stdin under cp1252 exited %d: %s" % (sent.returncode, combined(sent)))
        landed = store.files("mail/cloud/sess-b/")
        self.assertEqual(len(landed), 1, "one send should land one message file: %r" % landed)
        mid = message_id(landed[0])
        stored = store.read(landed[0])
        self.assertIn("ascii-ok", stored, "control: the stored message lacks the ASCII marker: %r" % stored)
        self.assertIn(ARROW, stored, "send from stdin under cp1252 stored the body garbled, not as UTF-8: %r" % stored)
        read = run_cli(receiver, "read", mid)
        self.assertEqual(read.returncode, 0, "mail read under cp1252 exited %d: %s" % (read.returncode, combined(read)))
        self.assertIn(BODY, read.stdout, "mail read under cp1252 did not return the body unchanged: %r" % read.stdout)

    def test_body_file_with_arrow_reads_back_unchanged_under_cp1252(self):
        store, sender, receiver = self.pair()
        sent = run_cli(sender, "send", "--to", "cloud/sess-b", "--kind", "request", "--body-file", self.body(MARKER))
        self.assertEqual(sent.returncode, 0,
                         "send from --body-file under cp1252 exited %d: %s" % (sent.returncode, combined(sent)))
        landed = store.files("mail/cloud/sess-b/")
        self.assertEqual(len(landed), 1, "one send should land one message file: %r" % landed)
        mid = message_id(landed[0])
        stored = store.read(landed[0])
        self.assertIn(ARROW, stored, "control: the --body-file send did not store the arrow: %r" % stored)
        read = run_cli(receiver, "read", mid)
        self.assertEqual(read.returncode, 0,
                         "mail read under cp1252 of a --body-file message exited %d, not 0: %s"
                         % (read.returncode, combined(read)))
        self.assertIn(BODY, read.stdout, "mail read under cp1252 did not return the body unchanged: %r" % read.stdout)

    def test_stderr_arrow_under_cp1252_reaches_stderr_as_utf8(self):
        """Stderr is reconfigured with stdin and stdout. A bad-use error that echoes an arrow must reach stderr as
        UTF-8: no UnicodeEncodeError, and no backslash escape in place of the arrow."""
        _, sender, _ = self.pair()
        bad = run_cli(sender, "send", "--to", "cloud/sess-b", "--kind", ARROW, "--body-file", "-")
        self.assertEqual(bad.returncode, 2, "an unknown --kind exited %d, not 2: %s" % (bad.returncode, combined(bad)))
        self.assertNotIn("UnicodeEncodeError", bad.stderr,
                         "the arrow in a bad-use error raised UnicodeEncodeError on stderr: %r" % bad.stderr)
        self.assertIn(ARROW, bad.stderr,
                      "the arrow in a bad-use error did not reach stderr as UTF-8: %r" % bad.stderr)


class StdinNotUtf8(MailCase):
    """`bin/mail send -` reads its body as UTF-8. Stdin that is not UTF-8 must end in "not sent:" with exit 1, never
    in an uncaught traceback, and must land no message."""

    def test_non_utf8_stdin_exits_1_with_not_sent_line_and_no_traceback(self):
        store = self.store()
        sender = self.machine("a", store, session="sess-a")
        # Strict, so the case reads the same stdin on any host locale. Scope before subject: a valid send first.
        sender.env["PYTHONIOENCODING"] = "utf-8:strict"
        control = run_cli(sender, "send", "--to", "cloud/sess-b", "--kind", "request", "--body-file", "-",
                          input_text=BODY)
        self.assertEqual(control.returncode, 0,
                         "control: a valid UTF-8 send from stdin exited %d: %s" % (control.returncode, combined(control)))
        landed = store.files("mail/cloud/sess-b/")
        self.assertEqual(len(landed), 1, "control: one valid send should land one message file: %r" % landed)
        bad = run_cli(sender, "send", "--to", "cloud/sess-b", "--kind", "request", "--body-file", "-",
                      input_bytes=b"\xff\xfe")
        self.assertEqual(bad.returncode, 1, "stdin bytes that are not UTF-8 exited %d, not 1: %s"
                         % (bad.returncode, combined(bad)))
        self.assertNotIn("Traceback", bad.stderr,
                         "stdin bytes that are not UTF-8 raised an uncaught traceback: %r" % bad.stderr)
        self.assertTrue([line for line in bad.stderr.splitlines() if line.startswith("not sent:")],
                        "stdin bytes that are not UTF-8 printed no 'not sent:' line on stderr: %r" % bad.stderr)
        self.assertEqual(store.files("mail/cloud/sess-b/"), landed,
                         "stdin bytes that are not UTF-8 landed a message on the mail ref")


class MailboxOff(MailCase):
    """With MAILBOX_REPO unset the mailbox is off: a turn prints nothing, and `mail read` exits 2 rather than
    reading the store as empty."""

    def test_unset_mailbox_repo_gives_no_turn_lines_and_read_exits_2(self):
        store = self.store()
        store.seed("cloud/sess-b", "0123456789ab", "request", "cloud/sess-a", "Body marker: off-switch")
        receiver = self.machine("b", store, session="sess-b")
        control = turn(receiver)
        self.assertEqual(len(listed_with(control, "0123456789ab")), 1,
                         "control: with MAILBOX_REPO set the turn does not list the seeded message: %r" % control)
        del receiver.env["MAILBOX_REPO"]
        lines = turn(receiver)
        self.assertEqual(lines, [], "MAILBOX_REPO unset: a turn start printed lines: %r" % lines)
        read = run_cli(receiver, "read", "0123456789ab")
        self.assertEqual(read.returncode, 2,
                         "MAILBOX_REPO unset: mail read exited %d, not 2: %s" % (read.returncode, combined(read)))


@unittest.skipIf(os.name == "nt", NT_NO_STUB)
class RefreshNotice(MailCase):
    """A batch merge mails one refresh notice: `mail/refresh/<owner>-<repo>/main.md` on the mail ref, whose body is
    `main moved to <sha>` (decision merge-mail-refreshes-sessions). A cloud session (CLAUDE_CODE_REMOTE=true) whose turn
    start sees the ref move reads it, runs the install once per new sha, and prints `main moved to <sha>; refreshed`.
    A failure prints a `mail unknown:` line, never a traceback. A local session ignores the notice. The install command
    is MAILBOX_REFRESH_COMMAND: run with no arguments and no shell, so the sha is never in a command."""

    def test_cloud_moved_turn_runs_the_install_once_and_says_refreshed(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        lines = turn(receiver)
        self.assertIn("main moved to %s; refreshed" % SHA_A, lines,
                      "a cloud session that saw a new main sha printed no 'refreshed' line: %r" % lines)
        self.assertEqual(len(read_lines(log)), 1,
                         "the install ran %d times for one new sha, expected once" % len(read_lines(log)))

    def test_a_second_turn_with_no_new_merge_runs_no_install_and_no_fetch(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        turn(receiver)
        self.assertEqual(len(read_lines(log)), 1,
                         "control: the first turn ran %d installs, expected 1" % len(read_lines(log)))
        with Starts() as again:
            lines = turn(receiver)
        self.assertEqual(len(read_lines(log)), 1,
                         "a turn with no new merge ran the install again: %d runs" % len(read_lines(log)))
        ran = [git_subcommand(args) for args in again.git_starts()]
        self.assertEqual(ran, ["ls-remote"], "a turn with no new merge ran git %r, expected only the tip check" % ran)
        self.assertFalse(any("refreshed" in line for line in lines), "a turn with no new merge said refreshed: %r" % lines)

    def test_a_move_that_keeps_the_installed_sha_runs_no_install(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        turn(receiver)
        self.assertEqual(len(read_lines(log)), 1,
                         "control: the first turn ran %d installs, expected 1" % len(read_lines(log)))
        store.seed("cloud/sess-c", "0a1b2c3d4e01", "inform", "cloud/sess-a", "Body marker: other mail\n")
        lines = turn(receiver)
        self.assertEqual(len(read_lines(log)), 1,
                         "the tip moved for other mail and the install ran again: %d runs" % len(read_lines(log)))
        self.assertFalse(any("refreshed" in line for line in lines), "a move for the same sha said refreshed: %r" % lines)

    def test_a_new_sha_runs_the_install_again_and_names_the_new_sha(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        turn(receiver)
        self.assertEqual(len(read_lines(log)), 1,
                         "control: the first turn ran %d installs, expected 1" % len(read_lines(log)))
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_B)
        lines = turn(receiver)
        self.assertIn("main moved to %s; refreshed" % SHA_B, lines,
                      "a new main sha printed no 'refreshed' line for that sha: %r" % lines)
        self.assertEqual(len(read_lines(log)), 2,
                         "a new main sha ran the install %d times in all, expected 2" % len(read_lines(log)))

    def test_a_local_session_ignores_the_notice_while_a_cloud_session_refreshes(self):
        store = self.store()
        cloud_script, cloud_log = fake_installer(self.case, "install-cloud")
        local_script, local_log = fake_installer(self.case, "install-local")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        cloud = self.cloud_machine(store, "b", "sess-b", cloud_script)
        local = self.machine("a", store, origin=ORIGIN)
        local.env["MAILBOX_REFRESH_COMMAND"] = local_script
        cloud_lines = turn(cloud)
        self.assertIn("main moved to %s; refreshed" % SHA_A, cloud_lines,
                      "control: the cloud session printed no 'refreshed' line: %r" % cloud_lines)
        local_lines = turn(local, session_id="sess-a")
        self.assertEqual(read_lines(local_log), [],
                         "a local session ran the install for the notice: %d runs" % len(read_lines(local_log)))
        self.assertFalse(any("refreshed" in line for line in local_lines),
                         "a local session said refreshed: %r" % local_lines)

    def test_a_notice_with_a_bad_sha_is_never_run_and_prints_mail_unknown(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        marker = os.path.join(self.case, "injected-marker")
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        for body in ("main moved to not-a-sha\n", "main moved to $(touch %s)\n" % shlex.quote(marker)):
            store.publish(REFRESH_PATH, body)
            lines = turn(receiver)
            self.assertEqual(read_lines(log), [], "a notice with a bad sha ran the install: body %r" % body)
            self.assertFalse(os.path.exists(marker), "a notice's text ran in a shell: body %r" % body)
            self.assertTrue(any(line.startswith(UNKNOWN) for line in lines),
                            "a notice with a bad sha printed no 'mail unknown' line: body %r, lines %r" % (body, lines))

    def test_a_failing_install_prints_refresh_failed_and_the_next_move_retries(self):
        store = self.store()
        flag = os.path.join(self.case, "install-works")
        script, log = fake_installer(self.case, "install", fail_until=flag)
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        lines = turn(receiver)
        self.assertEqual(len(read_lines(log)), 1,
                         "control: the failing install ran %d times, expected 1" % len(read_lines(log)))
        self.assertTrue(any(line.startswith(UNKNOWN + "refresh failed: ") for line in lines),
                        "a failed install printed no 'mail unknown: refresh failed:' line: %r" % lines)
        self.assertFalse(any("refreshed" in line for line in lines), "a failed install printed 'refreshed': %r" % lines)
        open(flag, "w").close()
        store.seed("cloud/sess-c", "0a1b2c3d4e02", "inform", "cloud/sess-a", "Body marker: move\n")
        lines = turn(receiver)
        self.assertEqual(len(read_lines(log)), 2,
                         "a move after a failed install did not retry the install: %d runs" % len(read_lines(log)))
        self.assertIn("main moved to %s; refreshed" % SHA_A, lines,
                      "the retried install printed no 'refreshed' line: %r" % lines)

    def test_a_hung_install_is_killed_at_the_bound_and_the_turn_says_refresh_failed(self):
        store = self.store()
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        fast, fast_log = fake_installer(self.case, "install-fast")
        hung, hung_log = fake_installer(self.case, "install-hung", hang_for=5)
        with mock.patch.object(MAIL_MODULE, "REFRESH_BOUND", 2):
            control = self.cloud_machine(store, "c", "sess-c", fast)
            control_lines = turn(control)
            self.assertIn("main moved to %s; refreshed" % SHA_A, control_lines,
                          "control: an install that ends within the bound printed no 'refreshed' line: %r" % control_lines)
            receiver = self.cloud_machine(store, "b", "sess-b", hung)
            lines = turn(receiver)
        self.assertTrue(os.path.exists(hung + ".pid"),
                        "control: the hung install never started, so there was nothing to kill: %r" % lines)
        self.assertNotIn("done", read_lines(hung_log),
                         "the hung install ran to its end past the bound, so the turn waited for it: log %r"
                         % read_lines(hung_log))
        with open(hung + ".pid", encoding="utf-8") as handle:
            pid = int(handle.read().strip())
        with self.assertRaises(ProcessLookupError, msg="the hung install's process outlived the turn: pid %d" % pid):
            os.kill(pid, 0)
        self.assertIn(UNKNOWN + "refresh failed: the install ran past 2 s", lines,
                      "a hung install printed no 'refresh failed' line for the bound: %r" % lines)
        installed = MAIL_MODULE.read_installed(receiver.env)
        self.assertEqual(installed, {}, "a hung install wrote its sha as installed: %r" % installed)

    def test_the_refresh_path_starts_only_the_install_and_no_timer_or_sleep(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        sleeps, threads = [], threading.active_count()
        with Starts() as moved, mock.patch.object(time, "sleep", side_effect=sleeps.append):
            lines = turn(receiver)
        self.assertEqual(len(read_lines(log)), 1, "control: the install did not run: %r" % lines)
        others = [args for args in moved.argv if program_name(args) != "git"]
        self.assertEqual(len(others), 1,
                         "the refresh path started %d processes that are not git, expected only the install" % len(others))
        self.assertIsInstance(others[0], list, "the install was started from a shell string, not an argv list: %r" % (others[0],))
        self.assertEqual(sleeps, [], "the refresh path slept: %r" % sleeps)
        self.assertLessEqual(threading.active_count(), threads, "the refresh path started a thread")

    def test_a_moved_cloud_turn_with_a_notice_keeps_its_git_bounds_within_ten_seconds(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        with Starts() as moved:
            lines = turn(receiver)
        self.assertIn("main moved to %s; refreshed" % SHA_A, lines, "control: the moved cloud turn printed no 'refreshed' line")
        self.assertTrue(moved.git_starts(), "control: the moved cloud turn started no git")
        self.assertNotIn(None, moved.git_bounds(), "a git start in the cloud turn has no timeout: %r" % moved.git_bounds())
        total = sum(moved.git_bounds())
        self.assertLessEqual(total, 10, "the moved cloud turn's git timeouts %r sum to %s s, over the 10 s bound"
                             % (moved.git_bounds(), total))

    def test_unset_mailbox_repo_gives_no_refresh_line_and_runs_no_install(self):
        store = self.store()
        script, log = fake_installer(self.case, "install")
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_A)
        receiver = self.cloud_machine(store, "b", "sess-b", script)
        control = turn(receiver)
        self.assertIn("main moved to %s; refreshed" % SHA_A, control,
                      "control: with MAILBOX_REPO set the cloud turn printed no 'refreshed' line: %r" % control)
        del receiver.env["MAILBOX_REPO"]
        store.publish(REFRESH_PATH, "main moved to %s\n" % SHA_B)
        lines = turn(receiver)
        self.assertEqual(lines, [], "MAILBOX_REPO unset: a turn start printed lines: %r" % lines)
        self.assertEqual(len(read_lines(log)), 1,
                         "MAILBOX_REPO unset: the install ran again: %d runs" % len(read_lines(log)))


class SettingsDefault(unittest.TestCase):
    """The mailbox store is a default of every session: settings.json `env` names it, so no session sets it by hand."""

    def test_settings_env_names_the_mailbox_store(self):
        with open(os.path.join(REPO, "settings.json"), encoding="utf-8") as handle:
            env = json.load(handle).get("env", {})
        self.assertEqual(env.get("MAILBOX_REPO"), "https://github.com/shivinate7/session-mailbox.git",
                         "settings.json env has no MAILBOX_REPO default, so a session reads no mail: %r" % env.get("MAILBOX_REPO"))


if __name__ == "__main__":
    try:
        program = unittest.main(exit=False)
    finally:
        tracked_tree.rm_tree(ROOT)  # test-temp-standard: teardown removes the run folder
    sys.exit(0 if program.result.wasSuccessful() else 1)
