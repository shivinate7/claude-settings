#!/usr/bin/env python3
"""Cases for the git mailbox: bin/mail (send, read, take) and hooks/mail.py (turn_start_lines).

Run it from the repository root:

    python3 hooks/test_mail.py

Standard library only, and no test runner. Each case runs against a bare store on a file:// URL
(MAILBOX_REPO) with one scratch cache per machine (MAILBOX_CACHE). No case sleeps or reads the clock.

Contract the builder codes against. Every case is red until the product exists.
- bin/mail send --to <addr> --kind request|inform|reply [--re <id>] --body-file F
  The sender's address is cloud/<CLAUDE_CODE_REMOTE_SESSION_ID>. It writes mail/<addr>/<id>.md on
  refs/heads/mail with plumbing only, never a working tree.
- bin/mail read [<id>]  prints the open messages, or one message with its body.
- bin/mail take <id>    one commit moves mail/<addr>/<id>.md to done/<addr>/<id>.md with a
  Taken-by: line. A taker that finds the path gone prints "taken by another" and exits non-zero.
- hooks/mail.py turn_start_lines(payload, env) -> list[str]. payload carries session_id and cwd;
  env carries MAILBOX_REPO, MAILBOX_CACHE and CLAUDE_CODE_REMOTE_SESSION_ID. Failure lines start
  "mail unknown: " and never say "no mail".
- A message file has line 1 `Msg <id> from <addr> to <addr> kind <kind> re <id|-> try <n>`, line 2
  `Reply-to: <addr>`, then the body. The fixtures write this format with plumbing.

Pinned choices (each one a departure or an open point, not settled by the spec):
1. Retry trigger. A push is retried only after a non-fast-forward, at most 5 retries, so 6 pushes
   in all. Any other refused push prints "not sent: <reason>" at once and exits 1 (the lane ruling).
2. A non-fast-forward on every try. Git forbids ref updates inside a pre-receive hook, and a
   server refusal reads "[remote rejected]", so the case pushes to a second store whose tip the
   sender never fetched. The client refuses each push itself, as "[rejected]", before it sends
   anything. Pushes are counted from the trace2 event log of the send.
3. An unchanged turn still lists open mail, from a listing the moved turn wrote. Its one git start
   is the remote check, and the turn writes no file.
4. A request stays listed after its reply lands, until take. An inform closes by take alone; that
   case asserts that take removes it from turn start and creates nothing else.
5. Only the cloud address form is covered. The pc/<host> form has no seam for a test.
6. The sweep of old run folders is proven in hooks/test_feedback_inbox.py. Not repeated here.

Every machine gets a git identity, as a configured Mac does. A machine with no identity is not covered.
"""
import importlib.util
import json
import os
import subprocess
import sys
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
SCRUBBED = ("CLAUDE_CODE_REMOTE_SESSION_ID", "MAILBOX_REPO", "MAILBOX_CACHE", "GIT_DIR",
            "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "CLAUDE_CODE_EXECPATH", "AI_AGENT")
IDENTITY = {"GIT_AUTHOR_NAME": "Mail Test", "GIT_AUTHOR_EMAIL": "mail-test@example.invalid",
            "GIT_COMMITTER_NAME": "Mail Test", "GIT_COMMITTER_EMAIL": "mail-test@example.invalid"}
UNKNOWN = "mail unknown: "


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
    return {key: value for key, value in os.environ.items() if key not in SCRUBBED}


def fixture_env(home, extra=None):
    """The env the fixture git calls run in: a scratch home, the identity, no prompts."""
    env = scrubbed_environ()
    env.update(IDENTITY)
    env.update({"HOME": home, "USERPROFILE": home, "XDG_CONFIG_HOME": home,
                "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
    env.update(extra or {})
    return env


def git(cwd, args, env, input_text=None):
    result = subprocess.run(["git", *args], cwd=cwd, env=env, input=input_text,
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=60)
    if result.returncode:
        raise RuntimeError("fixture git %s failed: %s" % (args[0], result.stderr.strip()))
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

    def files(self, prefix=""):
        tip = self.tip()
        if tip is None:
            return []
        listing = git(self.path, ["ls-tree", "-r", "--name-only", tip], self.env)
        return sorted(path for path in listing.splitlines() if path.startswith(prefix))

    def read(self, path):
        return git(self.path, ["show", "%s:%s" % (self.tip(), path)], self.env)

    def seed(self, addr, mid, kind, sender, body, re_id="-"):
        """Land one message on the mail ref with fixture plumbing, so a send bug cannot mask a read or take case."""
        text = ("Msg %s from %s to %s kind %s re %s try 1\nReply-to: %s\n\n%s\n"
                % (mid, sender, addr, kind, re_id, sender, body))
        index = os.path.join(self.path, "seed.index")
        env = dict(self.env, GIT_INDEX_FILE=index)
        if os.path.exists(index):
            os.remove(index)
        tip = self.tip()
        if tip is None:
            git(self.path, ["read-tree", "--empty"], env)
        else:
            git(self.path, ["read-tree", tip], env)
        blob = git(self.path, ["hash-object", "-w", "--stdin"], self.env, input_text=text).strip()
        git(self.path, ["update-index", "--add", "--cacheinfo",
                        "100644,%s,mail/%s/%s.md" % (blob, addr, mid)], env)
        tree = git(self.path, ["write-tree"], env).strip()
        commit_args = ["commit-tree", tree, "-m", "seed %s" % mid]
        if tip is not None:
            commit_args += ["-p", tip]
        commit = git(self.path, commit_args, self.env).strip()
        update = ["update-ref", REFUSED, commit] + ([tip] if tip is not None else [])
        git(self.path, update, self.env)


class Machine:
    """One machine: its own home, its own cache, and a scratch checkout as its working directory."""

    def __init__(self, case, name, repo_url, session=None, push_to=None, trace=None):
        self.name = name
        self.session = session
        self.home = os.path.join(case, name + "-home")
        self.cache = os.path.join(case, name + "-cache.git")
        self.checkout = os.path.join(case, name + "-checkout")
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.checkout, exist_ok=True)
        git(self.checkout, ["init", "-q"], fixture_env(self.home))
        env = scrubbed_environ()
        env.update(IDENTITY)
        env.update({"HOME": self.home, "USERPROFILE": self.home, "XDG_CONFIG_HOME": self.home,
                    "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
                    "MAILBOX_REPO": repo_url, "MAILBOX_CACHE": self.cache})
        if session is not None:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = session
        if push_to is not None:
            add_git_config(env, "url.%s.pushInsteadOf" % push_to, repo_url)
        if trace is not None:
            env["GIT_TRACE2_EVENT"] = trace
        self.env = env


class Starts:
    """Counts the processes started inside this block. Popen covers subprocess.run and the no-window wrapper."""

    def __init__(self):
        self.argv = []

    def __enter__(self):
        starts = self.argv
        real = subprocess.Popen

        class Counting(real):
            def __init__(self, args, *rest, **kwargs):
                starts.append(args)
                super().__init__(args, *rest, **kwargs)

        self.patch = mock.patch.object(subprocess, "Popen", Counting)
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()
        return False

    def git_starts(self):
        return [args for args in self.argv if program_name(args) == "git"]


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


def run_cli(machine, *args):
    return subprocess.run([sys.executable, MAIL_CLI, *args], env=machine.env,
                          cwd=machine.checkout, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)


def combined(result):
    return (result.stdout or "") + (result.stderr or "")


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return handle.read().splitlines()


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


def turn(machine):
    payload = {"session_id": machine.session, "cwd": machine.checkout,
               "hook_event_name": "UserPromptSubmit", "prompt": "continue"}
    with mock.patch.dict(os.environ, machine.env, clear=True):
        return turn_start_lines(payload, machine.env)


def listed_with(lines, mid):
    return [line for line in lines if mid in line]


class MailCase(unittest.TestCase):
    def setUp(self):
        self.case = os.path.join(ROOT, self.id().rsplit(".", 1)[-1])
        os.makedirs(self.case)
        self.counter = 0

    def tearDown(self):
        tracked_tree.rm_tree(self.case)

    def store(self, name="store"):
        return Store(self.case, name)

    def machine(self, name, store, session=None, push_to=None, trace=None):
        return Machine(self.case, name, store.url, session, push_to=push_to, trace=trace)

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


if __name__ == "__main__":
    try:
        program = unittest.main(exit=False)
    finally:
        tracked_tree.rm_tree(ROOT)  # test-temp-standard: teardown removes the run folder
    sys.exit(0 if program.result.wasSuccessful() else 1)
