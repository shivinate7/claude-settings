#!/usr/bin/env python3
"""Cases for hooks/lease.py, the one lease home: take, give back and lift a named lease held in git. Stdlib and unittest.

    python3 hooks/test_lease.py

A lease is the ref refs/heads/lease/NAME on the repo's remote. Its record is a commit with an empty tree, whose message
lines are `lease NAME`, `holder:`, `repo:`, `taken:` and `roster:`. Give back and lift push a released record, one with an
`expires: 0` line, and never delete the ref. Each case builds a bare remote and a clone under this run's folder, with no
network. Roster removal is not covered here; it has its own file.

Until hooks/lease.py exists, every case fails on the assert in `need()`, whose message names the missing module. A missing
module never reads as a pass or as an import error.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

try:
    import lease  # noqa: E402  the one lease home (hooks/lease.py)
except Exception:  # a missing or broken module: each case then fails on need()'s assert, never on this import
    lease = None

LEASE_CMD = os.path.join(HERE, "lease.py")
MISSING = "hooks/lease.py is missing: the lease module does not exist yet"
REAL_GIT = shutil.which("git")
NAME = "triage"
ALPHA = "session_alpha"
BETA = "session_beta"
CALLER_VARS = ("CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_SESSION_ID")  # the caller variables lease reads: stripped per case
GIT_OPTS = ["-c", "gc.auto=0", "-c", "user.name=lease-test", "-c", "user.email=lease-test@localhost"]
RUN_FOLDER = _test_temp.run_folder()

# Shims: a `git` on PATH that runs the real git after one extra step. Each is a POSIX shell script, so its cases skip on Windows.
# RACE_SHIM runs one take by another holder on the first push of the take under test. That take read the ref absent, and it
# loses its push. SLOW_SHIM is `exec sleep`, so the process a budget kills is the sleep itself, with no orphan holding a pipe.
RACE_SHIM = r'''#!/bin/sh
case " $* " in
  *" push "*)
    if [ ! -e "$RACE_MARK" ]; then
      : > "$RACE_MARK"
      "$RACE_PY" "$RACE_SCRIPT" > "$RACE_OUT" 2>&1
    fi
    ;;
esac
exec "$REAL_GIT" "$@"
'''
COUNT_SHIM = '#!/bin/sh\necho start >> "$COUNT_LOG"\nexec "$REAL_GIT" "$@"\n'
SLOW_SHIM = "#!/bin/sh\nexec sleep 20\n"


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def git(cwd, *args, stdin=None, check=True):
    """A git call for a fixture. It runs the real git by its absolute path, so a shim on PATH never sees fixture work."""
    return subprocess.run([REAL_GIT, *GIT_OPTS, *args], cwd=cwd, input=stdin, capture_output=True, text=True, check=check)


def write_shim(folder, text):
    """Write `git` into `folder` as an executable shell script, and return the folder for PATH."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "git")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o755)
    return folder


def count_starts(log):
    """How many git starts the COUNT_SHIM logged so far."""
    if not os.path.isfile(log):
        return 0
    with open(log, encoding="utf-8") as handle:
        return handle.read().count("start")


class LeaseBase(unittest.TestCase):
    def need(self):
        """The first line of every case. The module and its command must exist, or the case fails here, by name."""
        self.assertIsNotNone(lease, MISSING)
        self.assertTrue(os.path.isfile(LEASE_CMD), "hooks/lease.py is missing: the command file does not exist yet")


class LeaseCase(LeaseBase):
    """A bare remote and a clone of it under this run's folder. The caller's lease variables are stripped for the case."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="lease-case-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.base, True)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        for key in CALLER_VARS:
            os.environ.pop(key, None)
        self.remote = os.path.join(self.base, "remote.git")
        git(self.base, "init", "-q", "--bare", self.remote)
        self.repo = self.clone("repo")

    def clone(self, name):
        path = os.path.join(self.base, name)
        git(self.base, "clone", "-q", self.remote, path)
        return path

    def ref_sha(self):
        """The lease ref's sha on the fixture remote, or '' when the ref is absent."""
        return git(self.remote, "rev-parse", "-q", "--verify", "refs/heads/lease/" + NAME, check=False).stdout.strip()

    def ref_message(self):
        return git(self.remote, "log", "-1", "--format=%B", "refs/heads/lease/" + NAME).stdout

    def put_record(self, message):
        """Write a record commit with this message as the lease ref, and return its sha. A fixture: no lease module writes it."""
        tree = git(self.repo, "mktree", stdin="").stdout.strip()
        sha = git(self.repo, "commit-tree", tree, "-m", message).stdout.strip()
        git(self.repo, "push", "-q", "origin", sha + ":refs/heads/fixture-" + sha[:12])
        git(self.remote, "update-ref", "refs/heads/lease/" + NAME, sha)
        return sha

    def command(self, *args, remote="origin"):
        """Run hooks/lease.py against this case's clone. -> the finished process."""
        return subprocess.run([sys.executable, LEASE_CMD, *args, "--repo-dir", self.repo, "--remote", remote],
                              capture_output=True, text=True, timeout=60)


class LeaseTakeTest(LeaseCase):
    def test_a_take_on_an_absent_ref_takes_it(self):
        self.need()
        result = lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertEqual(result.status, "taken", "a take of an absent lease did not take it")
        self.assertEqual(result.holder, ALPHA, "the take did not name the taker as holder")
        record = lease.read(self.repo, "origin", NAME)
        self.assertIsNotNone(record, "a taken lease left no record on the remote")
        self.assertEqual(record.fields.get("holder"), ALPHA, "the record does not name the taker as holder")
        self.assertFalse(record.released, "a fresh take reads as released")

    def test_the_holder_taking_again_is_own_and_pushes_nothing(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        before = self.ref_sha()
        self.assertTrue(before, "control: the first take left no ref")
        result = lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertEqual(result.status, "own", "the holder's own take did not read own")
        self.assertEqual(self.ref_sha(), before, "the holder's own take pushed a new record")

    def test_another_holder_is_refused_and_named(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        before = self.ref_sha()
        other = self.clone("other")
        result = lease.take(other, "origin", NAME, BETA)
        self.assertEqual(result.status, "held", "a take of a live lease by another holder was not refused")
        self.assertEqual(result.holder, ALPHA, "the refusal did not name the holder")
        self.assertEqual(self.ref_sha(), before, "a refused take changed the record")

    def test_a_released_lease_can_be_taken_by_another(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertEqual(lease.give(self.repo, "origin", NAME, ALPHA), "given", "the holder's give back was not given")
        other = self.clone("other")
        result = lease.take(other, "origin", NAME, BETA)
        self.assertEqual(result.status, "taken", "a released lease was not taken")
        self.assertEqual(result.holder, BETA, "the take of a released lease did not name the new holder")

    def test_a_take_with_a_roster_stores_the_roster_line(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA, roster="triage")
        self.assertEqual(lease.read(self.repo, "origin", NAME).fields.get("roster"), "triage", "the roster line was not stored")


class LeaseConcurrentTakeTest(LeaseCase):
    @unittest.skipIf(os.name == "nt", "the race is a POSIX shell shim on PATH")
    def test_two_takes_that_both_saw_the_ref_absent_leave_one_winner(self):
        """The loser's take reads the ref absent, then ALPHA's take runs in the gap before the loser's push. The loser's push
        must lose, and the loser must read held and name ALPHA."""
        self.need()
        other = self.clone("other")
        folder = os.path.join(self.base, "race")
        race_script = os.path.join(folder, "race_take.py")
        race_out = os.path.join(folder, "race_out.txt")
        marker = os.path.join(folder, "fired")
        write_shim(folder, RACE_SHIM)
        os.makedirs(folder, exist_ok=True)
        with open(race_script, "w", encoding="utf-8") as handle:
            handle.write("import sys\nsys.path.insert(0, %r)\nimport lease\n"
                         "print(lease.take(%r, 'origin', %r, %r).status)\n" % (HERE, self.repo, NAME, ALPHA))
        env = {"PATH": folder + os.pathsep + os.environ.get("PATH", ""), "REAL_GIT": REAL_GIT, "RACE_MARK": marker,
               "RACE_PY": sys.executable, "RACE_SCRIPT": race_script, "RACE_OUT": race_out}
        with mock.patch.dict(os.environ, env):
            loser = lease.take(other, "origin", NAME, BETA)
        self.assertTrue(os.path.isfile(marker), "the winning take never ran in the gap before the loser's push")
        with open(race_out, encoding="utf-8") as handle:
            winner = handle.read().strip()
        self.assertEqual(winner, "taken", "the take that ran first did not win: " + winner)
        self.assertEqual(loser.status, "held", "the take that lost the race did not read held")
        self.assertEqual(loser.holder, ALPHA, "the take that lost the race did not name the winner")
        self.assertEqual(lease.read(self.repo, "origin", NAME).fields.get("holder"), ALPHA,
                         "the remote does not hold the winner's record")


class LeaseGiveTest(LeaseCase):
    def test_the_holder_gives_back_and_the_record_reads_released(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertEqual(lease.give(self.repo, "origin", NAME, ALPHA), "given", "the holder's give back was not given")
        record = lease.read(self.repo, "origin", NAME)
        self.assertIsNotNone(record, "a give back deleted the record instead of releasing it")
        self.assertTrue(record.released, "the give back did not release the record")

    def test_a_give_back_never_deletes_the_ref(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(self.ref_sha(), "control: the take left no ref")
        lease.give(self.repo, "origin", NAME, ALPHA)
        self.assertNotEqual(self.ref_sha(), "", "the give back removed the ref from the remote")

    def test_a_non_holder_cannot_give_back(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA), "control: the holder does not hold before the give back")
        other = self.clone("other")
        self.assertEqual(lease.give(other, "origin", NAME, BETA), "not-holder", "a caller who is not the holder gave the lease back")
        self.assertFalse(lease.read(self.repo, "origin", NAME).released, "a refused give back released the record")
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA), "the holder lost the lease after a refused give back")

    def test_a_give_with_no_lease_reads_free_and_creates_no_ref(self):
        self.need()
        self.assertEqual(lease.give(self.repo, "origin", NAME, ALPHA), "free", "a give with no lease did not read free")
        self.assertEqual(self.ref_sha(), "", "a give with no lease created a ref")


class LeaseLiftCorruptTest(LeaseCase):
    def test_lift_works_on_a_record_whose_message_is_junk(self):
        self.need()
        self.put_record("this is not a lease record\nno holder line here")
        self.assertEqual(lease.lift(self.repo, "origin", NAME), "lifted", "a lift refused a record with a junk message")
        record = lease.read(self.repo, "origin", NAME)
        self.assertIsNotNone(record, "the lift removed the ref")
        self.assertTrue(record.released, "the lift did not release the junk record")

    def test_lift_frees_a_live_lease_held_by_another(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA), "control: the holder does not hold before the lift")
        self.assertEqual(lease.lift(self.repo, "origin", NAME), "lifted", "a lift did not free a live lease")
        self.assertFalse(lease.holds(self.repo, "origin", NAME, ALPHA), "the lifted holder still holds the lease")
        self.assertEqual(lease.take(self.repo, "origin", NAME, BETA).status, "taken", "a lifted lease could not be taken")

    def test_a_hand_deleted_ref_reads_free(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        git(self.remote, "update-ref", "-d", "refs/heads/lease/" + NAME)
        self.assertIsNone(lease.read(self.repo, "origin", NAME), "a hand-deleted ref did not read as absent")
        self.assertFalse(lease.holds(self.repo, "origin", NAME, ALPHA), "a hand-deleted ref still holds for its old holder")
        self.assertEqual(lease.lift(self.repo, "origin", NAME), "free", "a lift of a hand-deleted ref did not read free")


class LeaseReadUnknownTest(LeaseCase):
    def test_read_raises_unknown_for_a_remote_that_does_not_exist(self):
        self.need()
        self.assertIsNone(lease.read(self.repo, "origin", NAME), "a free lease on a readable remote did not read as absent")
        missing = os.path.join(self.base, "no-such-remote.git")
        with self.assertRaises(lease.Unknown, msg="a read of a remote that does not exist did not raise Unknown"):
            lease.read(self.repo, missing, NAME)

    def test_holds_raises_unknown_for_a_remote_that_does_not_exist(self):
        self.need()
        self.assertFalse(lease.holds(self.repo, "origin", NAME, ALPHA), "a free lease held for a caller on a readable remote")
        missing = os.path.join(self.base, "no-such-remote.git")
        with self.assertRaises(lease.Unknown, msg="a holds read of a remote that does not exist did not raise Unknown"):
            lease.holds(self.repo, missing, NAME, ALPHA)

    def test_the_command_exits_2_when_the_read_is_unknown(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        readable = self.command("show", NAME)
        self.assertEqual(readable.returncode, 0, "show on a readable remote did not exit 0: " + readable.stdout + readable.stderr)
        missing = os.path.join(self.base, "no-such-remote.git")
        for verb, extra in (("show", []), ("take", ["--holder", BETA])):
            with self.subTest(verb=verb):
                run = self.command(verb, NAME, *extra, remote=missing)
                self.assertEqual(run.returncode, 2, verb + " on an unreadable remote did not exit 2: " + run.stdout + run.stderr)


class LeaseReadBudgetTest(LeaseCase):
    def test_the_default_budget_is_a_number_at_most_fifteen_seconds(self):
        self.need()
        budget = lease.READ_BUDGET_S
        self.assertIsInstance(budget, (int, float), "READ_BUDGET_S is not a number")
        self.assertTrue(0 < budget <= 15, "READ_BUDGET_S is %r, outside (0, 15]" % (budget,))

    @unittest.skipIf(os.name == "nt", "the slow git is a POSIX shell shim on PATH")
    def test_holds_raises_unknown_when_a_git_call_outlasts_the_budget(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA, budget_s=30),
                        "control: a holds read inside a generous budget did not hold")
        folder = write_shim(os.path.join(self.base, "slow"), SLOW_SHIM)
        with mock.patch.dict(os.environ, {"PATH": folder + os.pathsep + os.environ.get("PATH", "")}):
            with self.assertRaises(lease.Unknown, msg="a read that outlasted its budget did not raise Unknown"):
                lease.holds(self.repo, "origin", NAME, ALPHA, budget_s=0.5)


class LeaseHolderIdTest(LeaseBase):
    def test_a_cloud_id_becomes_session_x(self):
        self.need()
        self.assertEqual(lease.holder_id({"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_abc123"}), "session_abc123",
                         "a cloud id of the form cse_X was not read as session_X")

    def test_the_cloud_id_wins_over_the_local_id(self):
        self.need()
        env = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_abc123", "CLAUDE_CODE_SESSION_ID": "local-9"}
        self.assertEqual(lease.holder_id(env), "session_abc123", "the local id was used when a cloud id was set")

    def test_a_cloud_value_without_the_cse_form_is_not_used(self):
        self.need()
        env = {"CLAUDE_CODE_REMOTE_SESSION_ID": "abc123", "CLAUDE_CODE_SESSION_ID": "local-9"}
        self.assertEqual(lease.holder_id(env), "local-9", "a cloud value with no cse_ form was used as the holder id")

    def test_the_local_id_is_used_as_it_stands(self):
        self.need()
        self.assertEqual(lease.holder_id({"CLAUDE_CODE_SESSION_ID": "local-9"}), "local-9",
                         "the local session id was not used as it stands")

    def test_the_payload_id_is_used_only_when_no_env_id_is_set(self):
        self.need()
        self.assertEqual(lease.holder_id({}, payload_session_id="payload-7"), "payload-7",
                         "the payload id was not the fallback when no env id is set")
        self.assertEqual(lease.holder_id({"CLAUDE_CODE_SESSION_ID": "local-9"}, payload_session_id="payload-7"), "local-9",
                         "the payload id was used although the env id is set")

    def test_no_id_gives_none(self):
        self.need()
        self.assertIsNone(lease.holder_id({}), "a caller with no id was given a holder id")


class LeaseHoldsTest(LeaseCase):
    def test_the_holder_passes(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA), "the holder of a live lease did not pass holds")

    def test_another_id_does_not_pass(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA), "control: the holder did not pass holds")
        self.assertFalse(lease.holds(self.repo, "origin", NAME, BETA), "a caller who is not the holder passed holds")

    def test_a_released_record_holds_for_nobody(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA), "control: the live holder did not pass before the give back")
        lease.give(self.repo, "origin", NAME, ALPHA)
        self.assertFalse(lease.holds(self.repo, "origin", NAME, ALPHA), "the former holder still holds a released lease")
        self.assertFalse(lease.holds(self.repo, "origin", NAME, BETA), "a released lease holds for another caller")

    def test_a_name_with_no_lease_holds_for_nobody(self):
        self.need()
        self.assertFalse(lease.holds(self.repo, "origin", NAME, ALPHA), "a name with no lease holds for a caller")

    def test_a_record_with_no_holder_line_holds_for_nobody(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        self.assertTrue(lease.holds(self.repo, "origin", NAME, ALPHA), "control: the live holder did not pass before the junk record")
        self.put_record("this is not a lease record")
        self.assertFalse(lease.holds(self.repo, "origin", NAME, ALPHA), "a record that names no holder held for a caller")
        self.assertFalse(lease.holds(self.repo, "origin", NAME, BETA), "a record that names no holder held for another caller")


class LeaseNoExpiryTest(LeaseCase):
    def test_the_taken_record_has_no_expires_line_and_no_pid_line(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        lines = self.ref_message().splitlines()
        self.assertIn("holder: " + ALPHA, lines, "control: the taken record does not name its holder")
        self.assertFalse(any(line.startswith("expires:") for line in lines), "a taken record carries an expires line")
        self.assertFalse(any(line.startswith("pid:") for line in lines), "a taken record carries a pid line")

    def test_a_taken_record_reads_as_never_expiring(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        record = lease.read(self.repo, "origin", NAME)
        self.assertIsNotNone(record, "control: the taken lease left no record")
        self.assertFalse(record.released, "a taken record reads as released")
        self.assertNotIn("expires", record.fields, "a taken record has an expires field")
        self.assertNotIn("pid", record.fields, "a taken record has a pid field")

    def test_a_give_back_writes_expires_zero_as_the_released_line(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        lease.give(self.repo, "origin", NAME, ALPHA)
        self.assertIn("expires: 0", self.ref_message().splitlines(),
                      "a give back did not write the expires 0 line that releases the record")


class LeaseReadCost(LeaseCase):
    @unittest.skipIf(os.name == "nt", "the counting git is a POSIX shell shim on PATH")
    def test_holds_starts_git_at_most_three_times_then_at_most_twice_for_the_same_sha(self):
        self.need()
        other = self.clone("other")
        lease.take(other, "origin", NAME, BETA)  # the object is not in self.repo, so the first read may fetch it
        folder = write_shim(os.path.join(self.base, "count"), COUNT_SHIM)
        log = os.path.join(folder, "starts.log")
        env = {"PATH": folder + os.pathsep + os.environ.get("PATH", ""), "REAL_GIT": REAL_GIT, "COUNT_LOG": log}
        with mock.patch.dict(os.environ, env):
            before = count_starts(log)
            self.assertTrue(lease.holds(self.repo, "origin", NAME, BETA), "the holder did not pass holds on a first call")
            first = count_starts(log) - before
            before = count_starts(log)
            self.assertTrue(lease.holds(self.repo, "origin", NAME, BETA), "the holder did not pass holds on a second call")
            second = count_starts(log) - before
        self.assertGreaterEqual(first, 1, "the counting shim saw no git start on the first call, so the count proves nothing")
        self.assertLessEqual(first, 3, "a first holds call started git %d times" % first)
        self.assertLessEqual(second, 2, "a second holds call for the same sha started git %d times" % second)


class LeaseCommandTest(LeaseCase):
    def test_take_exits_0_when_taken_and_again_when_it_is_the_holders_own(self):
        self.need()
        first = self.command("take", NAME, "--holder", ALPHA)
        self.assertEqual(first.returncode, 0, "a take of a free lease did not exit 0: " + first.stdout + first.stderr)
        again = self.command("take", NAME, "--holder", ALPHA)
        self.assertEqual(again.returncode, 0, "the holder's own take did not exit 0: " + again.stdout + again.stderr)

    def test_a_take_by_another_holder_exits_1_and_names_the_holder_and_the_fix(self):
        self.need()
        self.assertEqual(self.command("take", NAME, "--holder", ALPHA).returncode, 0, "control: the first take did not exit 0")
        run = self.command("take", NAME, "--holder", BETA)
        self.assertEqual(run.returncode, 1, "a take of a held lease by another did not exit 1: " + run.stdout + run.stderr)
        text = run.stdout + run.stderr
        self.assertIn(ALPHA, text, "the held refusal did not name the holder")
        self.assertIn("ask the owner to lift", text, "the held refusal did not say to ask the owner to lift")

    def test_give_back_exits_0_for_the_holder_and_1_for_another(self):
        self.need()
        self.assertEqual(self.command("take", NAME, "--holder", ALPHA).returncode, 0, "control: the take did not exit 0")
        refused = self.command("give", NAME, "--holder", BETA)
        self.assertEqual(refused.returncode, 1, "a give back by a caller who is not the holder did not exit 1")
        given = self.command("give", NAME, "--holder", ALPHA)
        self.assertEqual(given.returncode, 0, "the holder's give back did not exit 0: " + given.stdout + given.stderr)

    def test_lift_exits_0_and_the_lifted_lease_is_then_takeable(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        lifted = self.command("lift", NAME)
        self.assertEqual(lifted.returncode, 0, "lift did not exit 0: " + lifted.stdout + lifted.stderr)
        self.assertEqual(lease.take(self.repo, "origin", NAME, BETA).status, "taken", "a lifted lease could not be taken")

    def test_show_exits_0_and_names_the_holder(self):
        self.need()
        lease.take(self.repo, "origin", NAME, ALPHA)
        run = self.command("show", NAME)
        self.assertEqual(run.returncode, 0, "show did not exit 0: " + run.stdout + run.stderr)
        self.assertIn(ALPHA, run.stdout + run.stderr, "show did not name the holder")


if __name__ == "__main__":
    unittest.main()
