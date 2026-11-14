#!/usr/bin/env python3
"""Cases for the GitHub quota back-off (step gh-quota-budget). A read whose reply says the REST quota is low waits for the reset, and
a CI wait that polls stops polling while the quota is low. The CI watch cases are in hooks/test_ci_wake.py, the one home of that loop.
The confirm cases (ConfirmFlow) run merge.main through GhHalf's gh shim in test_merge.py, the one home of that flow.

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
MERGE_OID = "e" * 40  # the merge commit the PUT makes
MERGED = dict(PR, state="closed", merged=True, merge_commit_sha=MERGE_OID)  # the pull request after the PUT lands
PR_ROUTE = "repos/{owner}/{repo}/pulls/7"  # the route as the fake gh sees it: no -R, so the working directory's repo
GET_PR = ("gh", "GET", PR_ROUTE)
PUT_MERGE = ("gh", "PUT", PR_ROUTE + "/merge")


def low_until_reset(now):
    """An empty quota (Remaining 0) until RESET, then a full one: the header keys of a `gh api -i` reply at fake time `now`."""
    return {"X_RateLimit_Limit": LIMIT, "X_RateLimit_Remaining": "0", "X_RateLimit_Reset": str(int(RESET))} if now < RESET else full(now)


def full(now):
    """A full quota (Remaining equal to Limit) in a fresh window that resets an hour on."""
    return {"X_RateLimit_Limit": LIMIT, "X_RateLimit_Remaining": LIMIT, "X_RateLimit_Reset": str(int(RESET + 3600))}


def low_reply(out, reset):
    """A `gh api -i` reply made low: Remaining 0 of LIMIT, the reset at `reset`. The reply's other headers and its body stay as the shim sent them."""
    m = re.match(r"HTTP/\S+ (\d{3})", out)
    if not m:  # a transport error has no header block, so no quota to make low
        return out
    headers, body = tm.merge.split_headers(out)
    headers = {k: v for k, v in headers.items() if not k.startswith("x-ratelimit-")}
    headers.update({"x-ratelimit-limit": LIMIT, "x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(reset))})
    return tm.gh_i(int(m.group(1)), body, **headers)


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
    (None: no quota headers). `quota_on`, a regex on the route, limits `quota` to the replies of the routes it matches; the others
    carry a full quota. `checks_at(now)` gives the check rows of HEAD. `first` scripts the first replies as (code, body, headers),
    headers as for `quota`. Every gh call is recorded as (fake time, args) in `calls`, the args without the leading `gh`. `events` holds
    the calls and the pauses in order: ("gh", method, route) and ("pause", seconds). The PUT of the merge makes the pull request read merged."""

    def __init__(self, test, quota=full, checks_at=green, first=(), quota_on=None):
        self.clock = tm.Clock(NOW)
        self.quota, self.checks_at, self.first, self.quota_on = quota, checks_at, list(first), quota_on
        self.calls, self.events, self.merged = [], [], False
        self.cwd = tm.workflow_folder(test, git=True)  # a checkout with no workflows: no job caps to read
        patch = unittest.mock.patch.object(tm.merge, "sh", self.sh)
        patch.start()
        test.addCleanup(patch.stop)

    def host(self):
        return tm.merge.Host(required=["checks"], base="main", minute=60, now=self.clock.now, pause=self.pause, cwd=self.cwd)

    def pause(self, seconds):
        """The host's pause: the event goes into `events` in order with the calls, then the fake clock moves on."""
        self.events.append(("pause", seconds))
        self.clock.pause(seconds)

    def sh(self, args, cwd=None, input=None, env=None, timeout=None, live_stderr=False):
        argv = list(args[1:] if args[:1] == ["gh"] else args)
        now = self.clock.now()
        self.calls.append((now, argv))
        path = argv[1] if argv[:1] == ["api"] else " ".join(argv[:2])
        self.events.append(("gh", argv[argv.index("-X") + 1] if "-X" in argv else "GET", path))
        if len(self.calls) > 300:  # a loop that never ends fails here, it does not hang the run
            raise AssertionError("runaway reads: more than 300 gh calls")
        if self.first:  # a scripted failure is gh's exit 1 with HTTP 403, the one failure these cases script (a rate limit)
            code, body, headers = self.first.pop(0)
        else:
            code, body = 0, self.route(argv)
            headers = self.quota(now) if self.quota_on is None or re.search(self.quota_on, path) else full(now)
        if "-i" not in argv:  # gh api prints no header block without -i
            return code, body
        return code, tm.gh_i(403 if code else 200, body, **(headers or {}))

    def route(self, argv):
        if argv[:2] == ["run", "list"]:
            return "[]"
        route = argv[1] if argv[:1] == ["api"] else ""
        if re.search(r"/pulls/7/merge$", route) and "PUT" in argv:  # the merge call lands
            self.merged = True
            return json.dumps({"merged": True, "sha": HEAD, "message": "Pull Request successfully merged"})
        if re.search(r"/pulls/7$", route):
            return json.dumps(MERGED if self.merged else PR)
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

    def test_a_read_with_the_quota_full_waits_for_nothing(self):  # control: a full quota adds no pause, no hold and no quota line
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

    def test_a_read_makes_one_gh_call_and_writes_no_file(self):  # cost control: a quota read adds exactly one gh call and writes no file
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

    def test_unknown_quota_headers_hold_no_read_past_the_rate_cap(self):  # control: unreadable quota headers read as unknown, so no wait passes the rate cap
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

    def test_a_rate_limit_403_with_a_far_reset_waits_no_longer_than_the_cap(self):  # control: a 403 with a far reset waits no longer than the rate cap
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

    def test_a_ci_wait_with_the_quota_full_keeps_its_poll_rhythm(self):  # control: a full quota keeps the CI poll rhythm, at least four polls in five minutes
        g = QuotaGh(self, quota=full, checks_at=pending_past_reset)
        with contextlib.redirect_stdout(io.StringIO()):
            ok, why = g.host().wait_checks(7, HEAD, 120)
        self.assertTrue(ok, why)
        polls = set(g.reads_between(NOW, NOW + 300))
        self.assertGreaterEqual(len(polls), 4, f"{len(polls)} poll times in the first five minutes, want at least four")

    def test_a_low_checks_read_holds_the_next_call_until_the_reset(self):  # control
        g = QuotaGh(self, quota=low_until_reset, quota_on=r"/check-runs$", checks_at=pending_past_reset)
        with contextlib.redirect_stdout(io.StringIO()):
            ok, why = g.host().wait_checks(7, HEAD, 120)
        self.assertTrue(ok, why)  # scope: the wait ran to its green check
        reads = [i for i, (_, argv) in enumerate(g.calls) if argv[1:2] and argv[1].endswith("/check-runs")]
        self.assertTrue(reads, "the wait never read the checks, so the low checks reply was never sent")  # scope
        i = reads[0]
        self.assertLess(g.calls[i][0], RESET, "the checks read came after the reset, so its low reply armed no hold")  # scope
        self.assertLess(i + 1, len(g.calls), "no gh call came after the low checks read")
        nxt = g.calls[i + 1][0]
        self.assertGreaterEqual(nxt, RESET, f"the call after the low checks read came at {nxt:.0f} s, before the quota reset at {RESET:.0f} s")


class QuotaMerge(unittest.TestCase):
    """Host.merge reads the pull request, checks it for BLOCKED or BEHIND, then sends the PUT. A low quota on that read must not hold the
    PUT: a pull request that turns BLOCKED or BEHIND in the hold would be merged through the admin bypass."""

    def test_a_low_quota_on_the_pr_read_holds_nothing_between_that_read_and_the_put(self):
        g = QuotaGh(self, quota=low_until_reset)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            oid, why = g.host().merge(7, "squash", HEAD)
        # scope: the merge was sent and landed, and the first call read the pull request while the quota was low
        self.assertEqual(oid, MERGE_OID, f"the merge did not land: {why}")
        self.assertEqual([e for e in g.events if e[0] == "gh"][0], GET_PR, "the first gh call was not the pull request read")
        self.assertLess(g.calls[0][0], RESET, "the pull request read came after the reset, so its low reply armed no hold")
        put_at = g.events.index(PUT_MERGE)
        pr_at = max(i for i in range(put_at) if g.events[i] == GET_PR)
        held = [e for e in g.events[pr_at + 1:put_at] if e[0] == "pause"]
        self.assertEqual(held, [], f"the quota hold paused between the pull request read and the PUT: {g.events[pr_at:put_at + 1]}")

    def test_a_merge_with_the_quota_full_is_sent_at_once_and_lands(self):  # control
        g = QuotaGh(self, quota=full)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            oid, why = g.host().merge(7, "squash", HEAD)
        self.assertEqual(oid, MERGE_OID, f"the merge did not land: {why}")  # scope
        self.assertEqual([e for e in g.events if e[0] == "pause"], [], "a merge with the quota full paused")
        self.assertEqual([t for t, argv in g.calls if "PUT" in argv], [NOW], "the PUT was not sent at once")

    def test_a_low_put_reply_holds_the_read_after_it(self):  # control: the PUT's own low reply arms the call after it, so the hold-off clears after the PUT
        g = QuotaGh(self, quota=low_until_reset, quota_on=r"/merge$")
        host = g.host()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            oid, why = host.merge(7, "squash", HEAD)
        self.assertEqual(oid, MERGE_OID, f"the merge did not land: {why}")  # scope
        puts = [i for i, (_, argv) in enumerate(g.calls) if "PUT" in argv]
        self.assertEqual(len(puts), 1, f"{len(puts)} PUTs, want the one merge call")  # scope
        self.assertLess(g.calls[puts[0]][0], RESET, "scope: the PUT came after the reset, so its low reply armed no hold")
        after = g.calls[puts[0] + 1][0]
        self.assertGreaterEqual(after, RESET, f"the read after the low PUT reply came at {after:.0f} s, before the quota reset at {RESET:.0f} s")

    def test_a_merge_that_stops_on_its_pr_read_clears_the_hold_off_for_the_calls_after_it(self):  # control: a Stop or NetStop in the stretch clears the hold-off
        for stop in (tm.merge.Stop("the pull request read stopped"), tm.merge.NetStop("the pull request read stopped")):
            with self.subTest(stop=type(stop).__name__):
                g = QuotaGh(self, quota=low_until_reset)
                host = g.host()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                        unittest.mock.patch.object(host, "pr", side_effect=stop):
                    with self.assertRaises(type(stop)):
                        host.merge(7, "squash", HEAD)
                    host.api("pulls/7")  # its low reply arms the call after it
                    host.api("pulls/7")
                self.assertEqual(len(g.calls), 2, f"{len(g.calls)} gh calls after the stop, want the two reads")  # scope
                second = g.calls[1][0]
                self.assertGreaterEqual(second, RESET, f"the read after a low reply came at {second:.0f} s, before the quota reset at {RESET:.0f} s: the hold-off outlived the stop")


class ConfirmFlow(tm.Env):
    """The confirm flow itself: merge.main on a real checkout with a real Host, through the gh shim of GhHalf (the fixture's home). A wrapper
    adds the events that the order is read from to calls.log, in the order they happen: a gh call's line (the shim's), LOW after a reply made
    low, BRAKE begin and BRAKE end around the batch brake, and PAUSE n for a pause of n seconds. Only the replies `low_rule` picks change."""

    def setUp(self):
        super().setUp()
        tm.gh_case_setup(self)
        self.in_brake, self.low_sent, self.brake_no = False, [], 0
        self.fail_brake, self.fail_text = None, None  # a case makes every api read of brake number fail_brake fail with fail_text
        self.low_rule = lambda argv: False  # a case says which api call's reply is low
        real_sh, real_brake = tm.merge.sh, tm.merge.batch_refusal

        def sh(args, *a, **kw):
            code, out = real_sh(args, *a, **kw)
            argv = args[1:] if args[:1] == ["gh"] else args
            if self.in_brake and self.brake_no == self.fail_brake and argv[:1] == ["api"]:
                return 1, self.fail_text
            if argv[:1] == ["api"] and "-i" in argv and self.low_rule(argv):
                self.low_sent.append(argv)
                self.mark("LOW")
                out = low_reply(out, self.now + 600)  # the reset is 600 s on: the hold waits 600 s
            return code, out

        def brake(host, n, base, head):
            self.brake_no += 1
            self.mark("BRAKE begin")
            self.in_brake = True
            try:
                return real_brake(host, n, base, head)
            finally:
                self.in_brake = False
                self.mark("BRAKE end")

        for name, fake in (("sh", sh), ("batch_refusal", brake)):
            patch = unittest.mock.patch.object(tm.merge, name, fake)
            patch.start()
            self.addCleanup(patch.stop)

    def mark(self, text):
        with open(os.path.join(self.state, "calls.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def events(self):
        with open(os.path.join(self.state, "calls.log"), encoding="utf-8") as f:
            return f.read().splitlines()

    def confirm(self):
        """-> (rc, output) of `merge 7 --confirm` on the fixture's Host, whose pauses go into the event order."""
        host = tm.GhHalf.gh_host(self, pause=lambda: self.mark("PAUSE %d" % self.paused[-1]))
        return self.run_merge("7", "--confirm", host=host)

    def test_a_low_reply_on_the_batch_brake_read_arms_no_hold_before_the_put(self):
        self.low_rule = lambda argv: self.in_brake and argv[:1] == ["api"]  # every read of the batch brake replies low
        rc, out = self.confirm()
        self.assertEqual(rc, 0, out)  # scope: the merge went through
        ev = self.events()
        put = next(i for i, line in enumerate(ev) if line.startswith("PUT pulls/7/merge"))  # scope
        begin = max(i for i in range(put) if ev[i] == "BRAKE begin")  # the batch brake read right before the PUT
        reads = [i for i in range(begin, put) if ev[i] == "GET pulls/7"]
        self.assertTrue(reads, f"scope: no pull request read between the batch brake and the PUT: {ev[begin:put + 1]}")
        pr = reads[0]
        self.assertIn("LOW", ev[begin:pr], f"scope: the batch brake's read did not reply low: {ev[begin:pr + 1]}")
        held = [line for line in ev[begin:pr] if line.startswith("PAUSE")]
        self.assertEqual(held, [], f"a hold was served between the batch brake read and the pull request read, so the PUT went out after a pause: {ev[begin:put + 1]}")

    def test_a_hold_armed_by_a_checks_read_is_served_before_the_batch_brake_read(self):  # control: a low checks read holds the call after it, before the brake
        self.low_rule = lambda argv: argv[1].endswith("/check-runs") and not self.low_sent  # the first checks read replies low
        rc, out = self.confirm()
        self.assertEqual(rc, 0, out)  # scope
        ev = self.events()
        checks = next(i for i, line in enumerate(ev) if re.match(r"GET commits/[0-9a-f]+/check-runs", line))  # scope
        self.assertEqual(ev[checks + 1], "LOW", f"scope: the first checks read did not reply low: {ev[checks:checks + 3]}")
        self.assertTrue(ev[checks + 2].startswith("PAUSE"), f"the call after the low checks read was {ev[checks + 2]!r}, not the hold")
        put = next(i for i, line in enumerate(ev) if line.startswith("PUT pulls/7/merge"))
        begin = max(i for i in range(put) if ev[i] == "BRAKE begin")
        self.assertGreater(begin, checks + 2, "the batch brake read came before the hold that the checks read armed was served")

    def test_a_low_put_reply_holds_the_read_after_the_put_in_the_confirm_flow(self):  # control: after the brake and the merge's own read, the PUT's low reply still holds the read after it
        self.low_rule = lambda argv: "PUT" in argv  # the merge call's reply is low
        rc, out = self.confirm()
        self.assertEqual(rc, 0, out)  # scope: the merge went through
        ev = self.events()
        put = next(i for i, line in enumerate(ev) if line.startswith("PUT pulls/7/merge"))
        self.assertEqual(ev[put + 1], "LOW", f"scope: the PUT's reply did not reply low: {ev[put:put + 3]}")
        self.assertTrue(ev[put + 2].startswith("PAUSE"), f"the call after the low PUT reply was {ev[put + 2]!r}, not the hold")
        self.assertEqual(ev[put + 3], "GET pulls/7 after-merge", f"the read after the hold was {ev[put + 3]!r}")

    def stop_in_the_second_brake(self, text):
        """Every api read of the second brake fails with `text`, so the run stops inside the brake. -> the Host the run used."""
        self.fail_brake, self.fail_text = 2, text
        host = tm.GhHalf.gh_host(self, pause=lambda: self.mark("PAUSE %d" % self.paused[-1]))
        rc, out = self.run_merge("7", "--confirm", host=host)
        ev = self.events()
        self.assertEqual(ev.count("BRAKE begin"), 2, "scope: the run did not reach the second brake")
        self.assertNotEqual(rc, 0, out)  # scope: the run stopped
        self.assertNotIn("PUT pulls/7/merge", " ".join(ev), "scope: a merge call went out")
        return host

    def hold_after_the_stop(self, host):
        """Every reply is low from here on. Two reads of the pull request, made by the same Host after the stop: the second waits."""
        self.low_rule = lambda argv: argv[:1] == ["api"]
        start = len(self.events())
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            host.api("pulls/7")
            host.api("pulls/7")
        tail = self.events()[start:]
        reads = [i for i, line in enumerate(tail) if line == "GET pulls/7"]
        self.assertEqual(len(reads), 2, f"scope: {len(reads)} reads after the stop, want two: {tail}")
        between = tail[reads[0]:reads[1]]
        self.assertIn("LOW", between, f"scope: the first read after the stop did not reply low: {between}")
        self.assertTrue(any(line.startswith("PAUSE") for line in between),
                        f"the second read after the stop went out at once, so the hold-off outlived the stop: {tail}")

    def test_a_plain_403_stop_in_the_second_brake_clears_the_hold_off_for_the_calls_after_it(self):  # control
        self.hold_after_the_stop(self.stop_in_the_second_brake(tm.PLAIN_403))

    def test_a_network_error_stop_in_the_second_brake_clears_the_hold_off_for_the_calls_after_it(self):  # control
        self.hold_after_the_stop(self.stop_in_the_second_brake(tm.NET_TLS))


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

    def test_inside_shared_deadline_a_low_quota_never_sleeps(self):  # control: a low quota never sleeps inside shared_deadline, which has no room for a pause
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

    def test_the_pace_has_no_default(self):  # the pace has no default, so a caller cannot copy POLL_PACE by leaving it out
        pace = inspect.signature(gh_quota.read).parameters["pace"]
        self.assertIs(pace.default, inspect.Parameter.empty,
                      f"gh_quota.read's pace defaults to {pace.default!r}: a caller that leaves it out copies that constant")

    def test_the_same_quota_is_low_at_a_30_s_pace_and_not_at_a_120_s_pace(self):  # control: the same quota reads low at a 30 s pace and not at 120 s, so pace sets the mark
        now = 1000.0
        headers = quota_headers(100, 3600, now)
        self.assertIsNotNone(gh_quota.read(headers, now, 30), "a 30 s caller reads 100 left against 3600 s to the reset as low (100 x 30 < 3600)")
        self.assertIsNone(gh_quota.read(headers, now, 120), "a 120 s caller reads 100 left against 3600 s to the reset as not low (100 x 120 >= 3600)")

    def test_the_mark_edges_are_exact(self):  # control: the low mark's edges are exact, so an off-by-one at the mark fails a row
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

    def test_a_wait_to_a_reset_past_the_cap_is_the_cap(self):  # control: a wait to a reset past the cap is the cap, so a far reset cannot hold a read past WAIT_CAP
        now = 1000.0
        got = gh_quota.read(quota_headers(0, 3600, now), now, 30)
        self.assertIsNotNone(got, "Remaining 0 with the reset 3600 s on read as not low")
        self.assertEqual(got[2], gh_quota.WAIT_CAP, f"the wait is {got[2]} s, want the cap of {gh_quota.WAIT_CAP} s, not the 3600 s to the reset")

    def test_a_fractional_wait_rounds_up_to_whole_seconds(self):  # control: a fractional wait rounds up to whole seconds, so 600.5 s waits 601 s
        now = 1000.5   # the reset is a whole epoch, so a fractional wait comes from a fractional now
        headers = {"x-ratelimit-limit": "15000", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1601"}
        got = gh_quota.read(headers, now, 30)
        self.assertIsNotNone(got, "Remaining 0 with the reset 600.5 s on read as not low")
        self.assertEqual(got[2], 601, f"the wait is {got[2]} s, want 601: 600.5 s to the reset rounds up")

    def test_the_merge_read_paces_by_its_own_settle_pause(self):  # control: the merge read paces its quota check by SETTLE_SECONDS, its own settle pause
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
