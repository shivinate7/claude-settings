#!/usr/bin/env python3
"""Fixture test for bin/sim-lease. Run: python3 lint/test_sim_lease.py -v

`sim-lease` is one lease on the shared simulator, with a queue. State is
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-lease.json` = {holder: {who, note, renewed_at, pid?} | null,
queue: [{who, note, asked_at}]}, with a sibling `sim-lease.lock`. Every call here runs the tool as a
subprocess with a temp HOME and no CLAUDE_CONFIG_DIR, and `SIM_LEASE_TTL_MIN` set per call: 1000 is
"fresh", 0 is "expired now". No case sleeps for expiry. `SIM_LEASE=PATH` points the suite at another tool.

Ambiguities in the contract that these cases pin, so the builder can object to them:
- `renewed_at` has sub-second resolution (TTL 0 means expired at the next call).
- A queue place in refusal text is 1-based: the second one in line reads "2".
- An expired holder that is not queue head cannot `take` again while someone else heads the queue.
- Refusal text names the holder and gives its time left; this suite looks for the holder's name, a word
  from expir/left/remain, and the place digit, since the layout is not fixed.

Every case calls `run`, which fails first when the tool is missing, so each case is red on the old code
for that one reason. Each refusal case also proves the allowed path, so a tool that always exits 1 fails too.
Temp paths come from this run's folder (test-temp-standard, lint/_test_temp.py; its sweep is proved in
test_find_copies.py).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
RUN_FOLDER = _test_temp.run_folder()
TOOL = os.environ.get("SIM_LEASE") or os.path.join(HERE, "..", "bin", "sim-lease")
FRESH, EXPIRED = "1000", "0"
A, B, C, D, E = ("agent-" + n for n in ("alpha", "bravo", "charlie", "delta", "echo"))
NOTE = "run the suite"
Result = namedtuple("Result", "rc out err")
# Holds each racer at a gate file, then starts them together; Python start-up alone would run them one by one.
GATE = 'while [ ! -e "$1" ]; do :; done; shift; exec "$@"'


def require_tool():
    if not os.path.exists(TOOL):
        raise AssertionError("bin/sim-lease does not exist: %s" % TOOL)


def tool_env(home, ttl, extra=None):
    """The tool's environment: a temp HOME, no CLAUDE_CONFIG_DIR (a live one would be this machine's real state)."""
    env = {k: v for k, v in os.environ.items() if k not in ("HOME", "CLAUDE_CONFIG_DIR", "SIM_LEASE_TTL_MIN")}
    env["HOME"] = home
    if ttl is not None:
        env["SIM_LEASE_TTL_MIN"] = str(ttl)
    env.update(extra or {})
    return env


def state_path(home):
    return os.path.join(home, ".claude", "state", "sim-lease.json")


class LeaseCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.home, True)

    def run_tool(self, *args, ttl=FRESH, extra=None):
        """Run bin/sim-lease itself, so its executable bit and shebang count. ttl None leaves the variable unset."""
        require_tool()
        done = subprocess.run([TOOL] + list(args), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              env=tool_env(self.home, ttl, extra), timeout=30)
        return Result(done.returncode, done.stdout, done.stderr)

    def state(self):
        with open(state_path(self.home), encoding="utf-8") as handle:
            return json.load(handle)

    def holder(self):
        return self.state()["holder"]

    def queue(self):
        return [entry["who"] for entry in self.state()["queue"]]

    def assertRc(self, result, want, label=""):
        self.assertEqual(result.rc, want, "%s rc=%s out=%r err=%r" % (label, result.rc, result.out, result.err))

    def lease(self, *args, **kw):
        """A setup call that must succeed."""
        result = self.run_tool(*args, **kw)
        self.assertRc(result, 0, "setup %s" % " ".join(args))
        return result


class StateFolder(LeaseCase):
    def test_state_lives_under_home_when_no_config_dir(self):
        self.lease("take", A)
        self.assertTrue(os.path.isdir(os.path.dirname(state_path(self.home))), "the tool makes state/ itself")
        holder = self.holder()
        self.assertEqual(holder["who"], A)
        self.assertIn("renewed_at", holder)
        self.assertEqual(self.queue(), [])
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(state_path(self.home)), "sim-lease.lock")),
                        "the lock is a sibling file sim-lease.lock")

    def test_claude_config_dir_wins(self):
        config = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, config, True)
        self.lease("take", A, extra={"CLAUDE_CONFIG_DIR": config})
        with open(os.path.join(config, "state", "sim-lease.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["holder"]["who"], A)
        self.assertFalse(os.path.exists(state_path(self.home)), "HOME/.claude must stay unused")


class Take(LeaseCase):
    def test_free_lease_goes_to_the_first_taker_and_holds_against_the_second(self):
        self.lease("take", A)
        refused = self.run_tool("take", B)
        self.assertRc(refused, 1)
        self.assertIn(A, refused.out)
        self.assertEqual(self.holder()["who"], A)

    def test_refusal_names_holder_expiry_and_queue_place(self):
        self.lease("take", A)
        for who in (B, C, D):
            self.lease("want", who, NOTE)
        c, d = self.run_tool("take", C), self.run_tool("take", D)
        self.assertRc(c, 1)
        self.assertRc(d, 1)
        for result in (c, d):
            self.assertIn(A, result.out)
            self.assertRegex(result.out, r"(?i)expir|left|remain")
        self.assertRegex(c.out, r"\b2\b", "C is second in line")
        self.assertRegex(d.out, r"\b3\b", "D is third in line")

    def test_default_ttl_is_not_zero(self):
        self.lease("take", A, ttl=None)
        self.assertRc(self.run_tool("take", B, ttl=None), 1)

    def test_expired_lease_lets_another_take_it(self):
        self.lease("take", A)
        self.assertRc(self.run_tool("take", B, ttl=FRESH), 1)
        self.lease("take", B, ttl=EXPIRED)
        self.assertEqual(self.holder()["who"], B)

    def test_holder_taking_again_renews(self):
        self.lease("take", A)
        self.lease("want", B, NOTE)
        before = self.holder()["renewed_at"]
        self.lease("take", A)
        holder = self.holder()
        self.assertEqual(holder["who"], A)
        self.assertGreater(holder["renewed_at"], before)
        self.assertEqual(self.queue(), [B], "a renew leaves the queue alone")


class QueueHead(LeaseCase):
    def test_free_lease_goes_to_the_head_not_a_later_entry_or_a_stranger(self):
        self.lease("want", B, NOTE)
        self.lease("want", C, NOTE)
        self.assertRc(self.run_tool("take", D), 1, "stranger")
        self.assertRc(self.run_tool("take", C), 1, "second in line")
        self.assertIsNone(self.holder())
        self.lease("take", B)
        self.assertEqual(self.holder()["who"], B)
        self.assertEqual(self.queue(), [C], "take removes the taker from the queue")

    def test_expired_lease_goes_to_the_head_and_the_expired_holder_waits_too(self):
        self.lease("take", A)
        self.lease("want", B, NOTE)
        self.lease("want", C, NOTE)
        self.assertRc(self.run_tool("take", C, ttl=EXPIRED), 1, "C is behind B")
        self.assertRc(self.run_tool("take", A, ttl=EXPIRED), 1, "expired holder A is not the head")
        self.assertEqual(self.holder()["who"], A)
        self.lease("take", B, ttl=EXPIRED)
        self.assertEqual(self.holder()["who"], B)
        self.assertEqual(self.queue(), [C])

    def test_fresh_holder_taking_again_is_not_blocked_by_the_queue(self):
        self.lease("take", A)
        self.lease("want", B, NOTE)
        self.lease("take", A)
        self.assertEqual(self.holder()["who"], A)

    def test_want_twice_is_one_entry_and_keeps_its_place(self):
        self.lease("want", B, NOTE)
        self.lease("want", C, NOTE)
        self.lease("want", B, NOTE)
        entries = self.state()["queue"]
        self.assertEqual([e["who"] for e in entries], [B, C])
        self.assertEqual(entries[0]["note"], NOTE)
        self.assertIn("asked_at", entries[0])

    def test_rank_puts_the_named_first_in_given_order_and_keeps_the_rest(self):
        self.lease("take", A)
        for who in (B, C, D, E):
            self.lease("want", who, NOTE)
        self.lease("rank", E, C)
        self.assertEqual(self.queue(), [E, C, B, D])
        self.assertEqual(self.holder()["who"], A)
        shown = self.lease("show").out
        places = [shown.index(who) for who in (E, C, B, D)]
        self.assertEqual(places, sorted(places), "show lists the queue in order")


class Renew(LeaseCase):
    def test_renew_records_pid_and_resets_the_clock(self):
        self.lease("take", A)
        before = self.holder()
        self.lease("renew", A, "--pid", str(os.getpid()))
        after = self.holder()
        self.assertEqual(after["who"], A)
        self.assertEqual(after["pid"], os.getpid())
        self.assertGreater(after["renewed_at"], before["renewed_at"])

    def test_live_pid_blocks_expiry_until_it_dies(self):
        child = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: (child.kill(), child.wait()))
        self.lease("take", A)
        self.lease("renew", A, "--pid", str(child.pid))
        self.assertEqual(self.holder()["pid"], child.pid)
        refused = self.run_tool("take", B, ttl=EXPIRED)
        self.assertRc(refused, 1, "the pid is alive")
        self.assertIn(A, refused.out)
        child.kill()
        child.wait()   # an unreaped child still answers kill(pid, 0)
        self.lease("take", B, ttl=EXPIRED)
        self.assertEqual(self.holder()["who"], B)

    def test_only_the_holder_renews_and_only_while_the_lease_is_live(self):
        self.assertRc(self.run_tool("renew", A), 1, "a free lease has no holder")
        self.lease("take", A)
        before = self.state()
        self.assertRc(self.run_tool("renew", B), 1, "B is not the holder")
        self.assertEqual(self.state(), before)
        self.assertRc(self.run_tool("renew", A, ttl=EXPIRED), 1, "A's lease is expired")
        self.lease("renew", A)
        self.lease("take", B, ttl=EXPIRED)
        self.assertEqual(self.holder()["who"], B)


class Release(LeaseCase):
    def test_release_frees_the_lease_and_prints_the_next_in_line(self):
        self.lease("take", A)
        self.lease("want", B, NOTE)
        self.lease("want", C, NOTE)
        released = self.lease("release", A)
        self.assertIn(B, released.out)
        self.assertNotIn(C, released.out)
        self.assertIsNone(self.holder())
        self.assertRc(self.run_tool("take", C), 1, "B heads the queue")
        self.lease("take", B)
        self.assertEqual(self.holder()["who"], B)

    def test_release_with_an_empty_queue(self):
        self.lease("take", A)
        self.lease("release", A)
        self.assertIsNone(self.holder())
        self.lease("take", B)

    def test_only_the_holder_releases(self):
        self.assertRc(self.run_tool("release", A), 1, "a free lease has no holder")
        self.lease("take", A)
        before = self.state()
        self.assertRc(self.run_tool("release", B), 1, "B is not the holder")
        self.assertEqual(self.state(), before)
        self.lease("release", A)
        self.assertIsNone(self.holder())


class Show(LeaseCase):
    def test_show_lists_holder_then_queue_in_order(self):
        self.lease("show")   # an empty home is not an error
        self.lease("take", A)
        self.lease("want", B, NOTE)
        self.lease("want", C, NOTE)
        out = self.lease("show").out
        self.assertTrue(out.index(A) < out.index(B) < out.index(C), out)
        self.assertRegex(out, r"(?i)expir|left|remain")


class Usage(LeaseCase):
    def test_bad_usage_exits_2_and_good_usage_does_not(self):
        for args in ([], ["bogus"], ["take"], ["renew"], ["release"], ["want"]):
            with self.subTest(args=args):
                self.assertRc(self.run_tool(*args), 2, "args %r" % (args,))
        self.assertRc(self.run_tool("show"), 0)


class Concurrency(LeaseCase):
    def test_ten_parallel_takes_on_a_free_lease_have_one_winner(self):
        require_tool()
        for round_no in range(5):
            home = tempfile.mkdtemp(dir=RUN_FOLDER)
            self.addCleanup(shutil.rmtree, home, True)
            gate = os.path.join(home, "go")
            names = ["agent-racer%s" % chr(ord("a") + i) for i in range(10)]
            racers = [subprocess.Popen(["sh", "-c", GATE, "sh", gate, TOOL, "take", who], env=tool_env(home, FRESH),
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True) for who in names]
            open(gate, "w").close()
            results = [(who, racer.communicate(timeout=60), racer.returncode) for who, racer in zip(names, racers)]
            codes = sorted(rc for _, _, rc in results)
            self.assertEqual(codes, [0] + [1] * 9, "round %d: %r" % (round_no, results))
            winner = next(who for who, _, rc in results if rc == 0)
            with open(state_path(home), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["holder"]["who"], winner, "round %d" % round_no)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)   # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    if os.name == "nt":
        print("SKIP sim-lease: a POSIX tool (fcntl)")
        sys.exit(0)
    unittest.main()
