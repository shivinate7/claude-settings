#!/usr/bin/env python3
"""Cases for the GitHub quota back-off (step gh-quota-budget). A read whose reply says the REST quota is low waits for the reset, and
a CI wait that polls stops polling while the quota is low. The CI watch cases are in hooks/test_ci_wake.py, the one home of that loop.

Run: python3 merge/test_merge_quota.py

The fixtures come from merge/test_merge.py (gh_i, Clock, workflow_folder, the rate texts): a case extends them, it does not copy them.
Importing it runs none of its cases. Each reply comes from a fake `gh` on merge.sh, the seam every gh call takes, so Host.gh, retry_net
and the wait run as they do in a merge. A fake clock moves only when the code pauses, so no case sleeps or reads the real clock.

What a reply carries: `gh api` prints its header block only with -i, as gh does. The quota is read from those headers, under
GitHub's names (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset as an epoch). The mark is never a fixed number: each case
uses an empty quota (Remaining 0) or a full one (Remaining equal to Limit), so any sane mark sorts them the same way.
"""
import contextlib, inspect, io, json, os, re, sys, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_merge as tm  # noqa: E402  the fixtures (gh_i, Clock, workflow_folder, RATE_API_403); importing it runs none of its cases
gh_quota = tm.merge.gh_quota  # the one home of the quota read (hooks/gh_quota.py)

NOW = 1000.0       # fake time of the first read
LIMIT = "5000"     # the REST quota of a user token
RESET = NOW + 600  # the quota's reset, 600 s on: inside the 900 s cap, so a wait to it is never capped
HEAD = "c" * 40
PR = {"number": 7, "head": {"sha": HEAD, "ref": "feat"}, "base": {"ref": "main"}, "state": "open", "draft": False,
      "mergeable": True, "mergeable_state": "clean", "body": "", "created_at": "2026-11-13T00:00:00Z", "changed_files": 1}


def low_until_reset(now):
    """An empty quota (Remaining 0) until RESET, then a full one: the header keys of a `gh api -i` reply at fake time `now`."""
    return {"X_RateLimit_Limit": LIMIT, "X_RateLimit_Remaining": "0", "X_RateLimit_Reset": str(int(RESET))} if now < RESET else full(now)


def full(now):
    """A full quota (Remaining equal to Limit) in a fresh window that resets an hour on."""
    return {"X_RateLimit_Limit": LIMIT, "X_RateLimit_Remaining": LIMIT, "X_RateLimit_Reset": str(int(RESET + 3600))}


def check_row(status, conclusion):
    return {"name": "checks", "status": status, "conclusion": conclusion, "details_url": None, "started_at": None, "completed_at": None}


def green(now):
    return [check_row("completed", "success")]


def pending_past_reset(now):
    """The one required check: pending until 200 s after the quota's reset, then green."""
    return [check_row("in_progress", None)] if now < RESET + 200 else [check_row("completed", "success")]


def tree(root):
    """Every folder and file under root: what a read must leave as it was."""
    return sorted(os.path.join(d, n) for d, dirs, files in os.walk(root) for n in dirs + files)


class QuotaGh:
    """A real Host whose gh is faked at merge.sh. `quota(now)` gives the header keys a `gh api -i` reply carries at fake time `now`
    (None: no quota headers). `checks_at(now)` gives the check rows of HEAD. `first` scripts the first replies as (code, body, headers),
    headers as for `quota`. Every gh call is recorded as (fake time, args) in `calls`, the args without the leading `gh`."""

    def __init__(self, test, quota=full, checks_at=green, first=()):
        self.clock = tm.Clock(NOW)
        self.quota, self.checks_at, self.first = quota, checks_at, list(first)
        self.calls, self.cwd = [], tm.workflow_folder(test, git=True)  # a checkout with no workflows: no job caps to read
        patch = unittest.mock.patch.object(tm.merge, "sh", self.sh)
        patch.start()
        test.addCleanup(patch.stop)

    def host(self):
        return tm.merge.Host(required=["checks"], base="main", minute=60, now=self.clock.now, pause=self.clock.pause, cwd=self.cwd)

    def sh(self, args, cwd=None, input=None, env=None, timeout=None, live_stderr=False):
        argv = list(args[1:] if args[:1] == ["gh"] else args)
        now = self.clock.now()
        self.calls.append((now, argv))
        if len(self.calls) > 300:  # a loop that never ends fails here, it does not hang the run
            raise AssertionError("runaway reads: more than 300 gh calls")
        if self.first:  # a scripted failure is gh's exit 1 with HTTP 403, the one failure these cases script (a rate limit)
            code, body, headers = self.first.pop(0)
        else:
            code, body, headers = 0, self.route(argv), self.quota(now)
        if "-i" not in argv:  # gh api prints no header block without -i
            return code, body
        return code, tm.gh_i(403 if code else 200, body, **(headers or {}))

    def route(self, argv):
        if argv[:2] == ["run", "list"]:
            return "[]"
        route = argv[1] if argv[:1] == ["api"] else ""
        if re.search(r"/pulls/7$", route):
            return json.dumps(PR)
        m = re.search(r"/commits/([0-9a-f]+)/(check-runs|status)$", route)
        if m and m.group(2) == "check-runs":
            return json.dumps({"check_runs": self.checks_at(self.clock.now())})
        if m:
            return json.dumps({"statuses": []})
        raise AssertionError("unexpected gh call: " + " ".join(argv))

    def reads_between(self, lo, hi):
        """The fake times of the gh calls strictly between lo and hi."""
        return [t for t, _ in self.calls if lo < t < hi]


class QuotaRead(unittest.TestCase):
    """A read whose reply says the quota is low waits for the reset before the next call, and says so in one line. A read with the
    quota full waits for nothing. The header read rides on the read: no extra call, no file."""

    def test_a_low_quota_read_waits_until_the_reset_before_the_next_call(self):
        g = QuotaGh(self, quota=low_until_reset)
        host = g.host()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            host.api("pulls/7")
            host.api("pulls/7")
        self.assertEqual(len(g.calls), 2, f"{len(g.calls)} gh calls, want the two reads")
        second = g.calls[1][0]
        self.assertGreaterEqual(second, RESET, f"the next read came at {second:.0f} s, before the quota reset at {RESET:.0f} s")

    def test_a_low_quota_read_says_so_in_one_line_before_the_next_call(self):
        g = QuotaGh(self, quota=low_until_reset)
        host, buf = g.host(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            host.api("pulls/7")
            before_next = buf.getvalue()  # everything printed by the first read, its wait included
            host.api("pulls/7")
        lines = [line for line in before_next.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, f"{len(lines)} lines printed before the next call, want one: {lines}")
        self.assertRegex(lines[0], r"(?i)quota|rate limit", "the one line does not name the low quota")

    def test_a_read_with_the_quota_full_waits_for_nothing(self):  # control: green on main
        g = QuotaGh(self, quota=full)
        host, buf = g.host(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            host.api("pulls/7")
            host.api("pulls/7")
        self.assertEqual(g.clock.pauses, [], "a read with the quota full paused")
        self.assertEqual([t for t, _ in g.calls], [NOW, NOW], "a read with the quota full was held back")
        self.assertNotRegex(buf.getvalue(), r"(?i)quota|rate limit", "a read with the quota full named the quota")

    def test_the_read_asks_for_its_headers_in_the_same_call(self):
        g = QuotaGh(self, quota=low_until_reset)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            g.host().api("pulls/7")
        self.assertEqual(len(g.calls), 1, f"one read made {len(g.calls)} gh calls")
        self.assertIn("-i", g.calls[0][1], "the read asked for no headers, so the quota cannot be read from it")

    def test_a_read_makes_one_gh_call_and_writes_no_file(self):  # cost control: green on main
        g = QuotaGh(self, quota=low_until_reset)
        before = tree(g.cwd)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            g.host().api("pulls/7")
        self.assertEqual(len(g.calls), 1, f"one read made {len(g.calls)} gh calls: the quota read must add none")
        self.assertEqual(tree(g.cwd), before, "the read wrote a file")


UNKNOWN_HEADERS = {
    "headers missing": {},
    "Remaining not a number": {"X_RateLimit_Remaining": "lots", "X_RateLimit_Reset": str(int(RESET))},
    "Remaining negative": {"X_RateLimit_Remaining": "-1", "X_RateLimit_Reset": str(int(RESET))},
    "reset not a number": {"X_RateLimit_Remaining": "0", "X_RateLimit_Reset": "soon"},
    "reset already past": {"X_RateLimit_Remaining": "0", "X_RateLimit_Reset": str(int(NOW - 100))},
}


class QuotaUnknown(unittest.TestCase):
    """Headers that cannot be read as a quota read as unknown: a read still returns, and no wait is longer than the rate cap."""

    def test_unknown_quota_headers_hold_no_read_past_the_rate_cap(self):  # control: green on main
        for label, keys in UNKNOWN_HEADERS.items():
            with self.subTest(headers=label):
                g = QuotaGh(self, quota=lambda now, keys=keys: keys)
                host = g.host()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    for _ in range(3):
                        code, _ = host.api("pulls/7")
                        self.assertEqual(code, 0, "a read with unknown quota headers failed")
                waits = g.clock.pauses
                self.assertTrue(all(0 <= w <= tm.merge.RATE_LADDER[-1] for w in waits), f"a wait past the cap: {waits}")

    def test_a_rate_limit_403_with_a_far_reset_waits_no_longer_than_the_cap(self):  # control: green on main
        far = {"X_RateLimit_Limit": LIMIT, "X_RateLimit_Remaining": "0", "X_RateLimit_Reset": str(int(NOW + 86400))}
        g = QuotaGh(self, first=[(1, tm.RATE_API_403, far)])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code, _ = g.host().api("pulls/7")
        self.assertEqual(code, 0)
        self.assertEqual(len(g.clock.pauses), 1, f"waits {g.clock.pauses}, want one")
        self.assertTrue(0 < g.clock.pauses[0] <= tm.merge.RATE_LADDER[-1], f"the wait is {g.clock.pauses[0]} s, past the cap")


class QuotaCiWait(unittest.TestCase):
    """The CI wait (Host.wait_checks) polls while the quota is low, and keeps its rhythm while it is full."""

    def test_a_ci_wait_makes_no_read_while_the_quota_is_low(self):
        g = QuotaGh(self, quota=low_until_reset, checks_at=pending_past_reset)
        with contextlib.redirect_stdout(io.StringIO()):
            ok, why = g.host().wait_checks(7, HEAD, 120)
        self.assertTrue(ok, why)  # scope: the wait ran to its green check
        self.assertGreaterEqual(g.clock.now(), RESET, "the wait ended before the quota reset, so the low window was never reached")
        reads = g.reads_between(NOW, RESET)
        self.assertEqual(reads, [], f"{len(reads)} gh reads while the quota was low, from {NOW:.0f} s to the reset at {RESET:.0f} s")

    def test_a_ci_wait_with_the_quota_full_keeps_its_poll_rhythm(self):  # control: green on main
        g = QuotaGh(self, quota=full, checks_at=pending_past_reset)
        with contextlib.redirect_stdout(io.StringIO()):
            ok, why = g.host().wait_checks(7, HEAD, 120)
        self.assertTrue(ok, why)
        polls = set(g.reads_between(NOW, NOW + 300))
        self.assertGreaterEqual(len(polls), 4, f"{len(polls)} poll times in the first five minutes, want at least four")


class QuotaInsideDeadline(unittest.TestCase):
    """Inside shared_deadline (the guard hook's budget) a low quota is reported, and no pause is taken."""

    def test_inside_shared_deadline_a_low_quota_is_reported(self):
        g = QuotaGh(self, quota=low_until_reset)
        host, buf = g.host(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf), tm.merge.shared_deadline(60):
            host.api("pulls/7")
        self.assertRegex(buf.getvalue(), r"(?i)quota|rate limit", "the low quota was not reported inside shared_deadline")

    def test_inside_shared_deadline_the_low_line_goes_to_stderr_not_stdout(self):
        """The guard's stdout is its JSON decision, so the low line goes to stderr only."""
        g = QuotaGh(self, quota=low_until_reset)
        host, out, err = g.host(), io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), tm.merge.shared_deadline(60):
            host.api("pulls/7")
        self.assertRegex(out.getvalue() + err.getvalue(), r"(?i)quota", "no low line was printed at all, on either stream")
        self.assertEqual(out.getvalue(), "", f"the low line is on the guard's stdout, which holds its JSON decision: {out.getvalue()!r}")
        self.assertRegex(err.getvalue(), r"(?i)quota", "the low line is not on stderr")

    def test_inside_shared_deadline_a_low_quota_never_sleeps(self):  # control: green on main
        g = QuotaGh(self, quota=low_until_reset)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), tm.merge.shared_deadline(60):
            code, _ = g.host().api("pulls/7")
        self.assertEqual(code, 0)
        self.assertEqual(g.clock.pauses, [], f"a pause of {g.clock.pauses} inside shared_deadline, which has no room for one")


def quota_headers(left, to_reset, now, limit=15000):
    """The header block of gh_quota.read, lower-case as split_headers gives it: Remaining `left` of `limit`, the reset `to_reset` s on."""
    return {"x-ratelimit-limit": str(limit), "x-ratelimit-remaining": str(left), "x-ratelimit-reset": str(int(now + to_reset))}


class QuotaMark(unittest.TestCase):
    """The low mark of gh_quota.read, derived from the caller's pace: a quota is low when what is left cannot cover the reads the caller
    makes before the reset, one every `pace` seconds. The pace is each caller's own, passed in, and has no default a caller could copy.
    Every case here passes its pace. The exact edges of the mark are pinned, so a mutant of `>=` or of the bounds fails a row."""

    def test_the_pace_has_no_default(self):  # red on 878cc8433: pace defaults to POLL_PACE
        pace = inspect.signature(gh_quota.read).parameters["pace"]
        self.assertIs(pace.default, inspect.Parameter.empty,
                      f"gh_quota.read's pace defaults to {pace.default!r}: a caller that leaves it out copies that constant")

    def test_the_same_quota_is_low_at_a_30_s_pace_and_not_at_a_120_s_pace(self):  # control: green on main
        now = 1000.0
        headers = quota_headers(100, 3600, now)
        self.assertIsNotNone(gh_quota.read(headers, now, 30), "a 30 s caller reads 100 left against 3600 s to the reset as low (100 x 30 < 3600)")
        self.assertIsNone(gh_quota.read(headers, now, 120), "a 120 s caller reads 100 left against 3600 s to the reset as not low (100 x 120 >= 3600)")

    def test_the_mark_edges_are_exact(self):  # control: green on main
        now = 1000.0
        rows = [
            ("at the mark: 100 reads at 30 s cover 3000 s exactly", 100, 3000, False),
            ("one second past the mark", 100, 3001, True),
            ("Remaining 0, reset 1 s on", 0, 1, True),
            ("Remaining 0, reset now", 0, 0, False),
            ("Remaining 0, reset 1 s past", 0, -1, False),
            ("Remaining -1, outside 0..Limit, reset 600 s on", -1, 600, False),
            ("Remaining equal to Limit", 15000, 3600, False),
            ("Remaining above Limit", 15001, 3600, False),
        ]
        for label, left, to_reset, low_wanted in rows:
            with self.subTest(label):
                got = gh_quota.read(quota_headers(left, to_reset, now), now, 30)
                if low_wanted:
                    self.assertIsNotNone(got, f"{label}: read as not low, want low")
                else:
                    self.assertIsNone(got, f"{label}: read as low, want not low or unknown: {got!r}")

    def test_a_wait_to_a_reset_past_the_cap_is_the_cap(self):  # control: green on 9640fa9a6, its mutant without the cap is the red
        now = 1000.0
        got = gh_quota.read(quota_headers(0, 3600, now), now, 30)
        self.assertIsNotNone(got, "Remaining 0 with the reset 3600 s on read as not low")
        self.assertEqual(got[2], gh_quota.WAIT_CAP, f"the wait is {got[2]} s, want the cap of {gh_quota.WAIT_CAP} s, not the 3600 s to the reset")

    def test_a_fractional_wait_rounds_up_to_whole_seconds(self):  # control: green on 9640fa9a6, its mutant that truncates is the red
        now = 1000.5   # the reset is a whole epoch, so a fractional wait comes from a fractional now
        headers = {"x-ratelimit-limit": "15000", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1601"}
        got = gh_quota.read(headers, now, 30)
        self.assertIsNotNone(got, "Remaining 0 with the reset 600.5 s on read as not low")
        self.assertEqual(got[2], 601, f"the wait is {got[2]} s, want 601: 600.5 s to the reset rounds up")

    def test_the_merge_read_paces_by_its_own_settle_pause(self):  # control: green on main
        g = QuotaGh(self, quota=low_until_reset)
        host = g.host()
        with unittest.mock.patch.object(tm.merge.gh_quota, "read", wraps=gh_quota.read) as spy, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            host.api("pulls/7")
        self.assertTrue(spy.called, "the merge read never reached gh_quota.read")
        args, kwargs = spy.call_args
        pace = kwargs["pace"] if "pace" in kwargs else args[2]
        self.assertEqual(pace, tm.merge.SETTLE_SECONDS, f"the merge read paced the quota check at {pace!r} s, not its settle pause")


if __name__ == "__main__":
    unittest.main()
