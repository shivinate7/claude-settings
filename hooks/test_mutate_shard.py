#!/usr/bin/env python3
"""Cases for the shard switch of the guard mutation test (MUTATE_SHARD=i/n). Standard library only, unittest style.

    python3 hooks/test_mutate_shard.py

The interface, as the builder implements it. This file pins it.

- parse_shard(value) in hooks/mutate_shared.py reads "i/n", with 1 <= i <= n, as (i, n).
  An empty value, which is an unset MUTATE_SHARD, reads as (1, 1): every mutant.
  Any other value raises ValueError.
- shard_of(items, (i, n)) in hooks/mutate_shared.py returns the items at positions i-1, i-1+n and so on.
  Shards 1 to n cover each item once.
- main() in hooks/mutate_guard.py reads MUTATE_SHARD through parse_shard and shard_of.
  It passes the shard to run_mutants and to run_controls.
  A bad value, or an empty shard, prints an ERROR line that names MUTATE_SHARD and returns 1 before any mutant runs.
  The anchor and collision pre-checks read the full MUTATIONS list, whatever the shard.

The main-level cases replace run_mutants, so no mutant runs and no suite starts.
Each case reads what main() hands to it.
The work folder that main() makes goes in this module's run folder (test-temp-standard).
"""
import contextlib
import io
import os
import shutil
import sys
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402
import mutate_guard  # noqa: E402
import mutate_shared  # noqa: E402

RUN = ""  # this run's folder, made in setUpModule and removed in tearDownModule
BAD_VALUES = ("bogus", "1", "0/2", "3/2", "1/0", "a/b", "1/2/3", "-1/2", "2/")


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


def fresh():
    """A new empty folder under this module's run folder."""
    folder = os.path.join(RUN, uuid.uuid4().hex)
    os.makedirs(folder)
    return folder


def labels(entries):
    return [mutate_guard.mutation_parts(entry)[0] for entry in entries]


def target_of(entry):
    return mutate_guard.mutation_parts(entry)[3]


def runnable(entry):
    return mutate_shared.skip_reason(mutate_guard.mutation_parts(entry)[5]) is None


def with_old(entry, old):
    """The entry with its anchor text set to `old`. Its other fields stay as they are."""
    label, _old, new, target, required, only_on = mutate_guard.mutation_parts(entry)
    return (label, old, new, target, required, only_on)


def run_main(shard=None, mutations=None):
    """Run main() with MUTATE_SHARD set to `shard`, or unset for None, and run_mutants replaced.

    `mutations` replaces MUTATIONS for the call. Return (exit code, the run_mutants mock, stdout).
    """
    out = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ))
        os.environ.pop("MUTATE_SHARD", None)
        if shard is not None:
            os.environ["MUTATE_SHARD"] = shard
        run = stack.enter_context(mock.patch.object(mutate_shared, "run_mutants", return_value=0))
        if mutations is not None:
            stack.enter_context(mock.patch.object(mutate_guard, "MUTATIONS", mutations))
        stack.enter_context(mock.patch.object(sys, "argv", ["mutate_guard.py"]))
        stack.enter_context(mock.patch.object(mutate_guard.tempfile, "mkdtemp", return_value=fresh()))
        stack.enter_context(contextlib.redirect_stdout(out))
        code = mutate_guard.main()
    return code, run, out.getvalue()


def mismatch(got, want):
    """Why the labels `got` differ from `want`, in one short line. None when they are equal."""
    if got == want:
        return None
    if len(got) != len(want):
        return "%d mutants, want %d" % (len(got), len(want))
    first = next(i for i, (g, w) in enumerate(zip(got, want)) if g != w)
    return "mutant %d is %r, want %r" % (first, got[first], want[first])


def entries_run(run):
    """The entries main() handed to run_mutants, or an empty list when it was not called."""
    return list(run.call_args[0][0]) if run.called else []


def controls_run(run):
    """The target keys of the controls main() handed to run_mutants, or an empty set when it was not called."""
    return set(run.call_args[1]["controls"]) if run.called else set()


class ShardSwitch(unittest.TestCase):
    """The helpers of hooks/mutate_shared.py that the switch is built from. They are pinned here by name."""

    def test_parse_shard_reads_i_of_n_and_an_unset_value_is_every_mutant(self):
        self.assertEqual(mutate_shared.parse_shard("2/3"), (2, 3))
        self.assertEqual(mutate_shared.parse_shard("1/1"), (1, 1))
        self.assertEqual(mutate_shared.parse_shard(""), (1, 1),
                         "an unset MUTATE_SHARD reads as no shard, so a local run would run nothing")

    def test_parse_shard_rejects_every_other_value(self):
        for value in BAD_VALUES:
            with self.subTest(value=value):
                with self.assertRaises(ValueError,
                                       msg="a bad value parses as a shard, so the run goes on with an unasked slice"):
                    mutate_shared.parse_shard(value)

    def test_shard_of_takes_every_nth_item_from_its_first_and_an_empty_shard_is_empty(self):
        self.assertEqual(mutate_shared.shard_of(list("abcdefg"), (2, 3)), ["b", "e"])
        self.assertEqual(mutate_shared.shard_of([1, 2], (3, 3)), [],
                         "a shard past the item count takes items from a shard that is not empty")

    def test_the_shards_cover_each_mutant_once(self):
        items = list(range(len(mutate_guard.MUTATIONS)))
        for n in (1, 2, 3, 5, 7):
            shards = [mutate_shared.shard_of(items, (i, n)) for i in range(1, n + 1)]
            with self.subTest(n=n):
                self.assertEqual(sorted(sum(shards, [])), items,
                                 "a mutant sits in two shards or in none, so it runs twice or never")


class ShardMain(unittest.TestCase):
    """main() of hooks/mutate_guard.py, with run_mutants replaced. The shard cases are red without the switch."""

    def test_an_unset_shard_runs_every_mutant(self):
        code, run, _out = run_main(None)
        self.assertEqual(code, 0)
        self.assertIsNone(mismatch(labels(entries_run(run)), labels(mutate_guard.MUTATIONS)),
                          "an unset MUTATE_SHARD runs fewer mutants than MUTATIONS")

    def test_each_mutant_runs_in_exactly_one_shard(self):
        for n in (2, 3):
            ran = []
            for i in range(1, n + 1):
                _code, run, _out = run_main(f"{i}/{n}")
                got = labels(entries_run(run))
                ran += got
                with self.subTest(shard=f"{i}/{n}"):
                    self.assertIsNone(mismatch(got, labels(mutate_guard.MUTATIONS[i - 1::n])),
                                      "shard %d of %d ran other mutants" % (i, n))
            with self.subTest(shards=n):
                self.assertIsNone(mismatch(sorted(ran), sorted(labels(mutate_guard.MUTATIONS))),
                                  "a mutant ran in two shards or in none, of %d" % n)

    def test_a_shard_builds_controls_for_its_own_targets_only(self):
        first = {}
        for entry in mutate_guard.MUTATIONS:
            if runnable(entry):
                first.setdefault(target_of(entry), entry)
        (_target_a, entry_a), (target_b, entry_b) = list(first.items())[:2]
        code, run, _out = run_main("2/2", [entry_a, entry_b])
        self.assertEqual(code, 0)
        self.assertEqual(controls_run(run), {target_b},
                         "a control is built for a target that no mutant of this shard has")

    def test_a_bad_value_stops_the_run_before_any_mutant(self):
        for value in BAD_VALUES:
            with self.subTest(value=value):
                code, run, out = run_main(value)
                self.assertEqual(code, 1, "a bad MUTATE_SHARD exits %d, want 1: the run goes on" % code)
                self.assertFalse(run.called, "a mutant ran after a bad MUTATE_SHARD")
                self.assertIn("MUTATE_SHARD", out, "a bad MUTATE_SHARD prints no line that names it")

    def test_an_empty_shard_exits_1_before_any_mutant(self):
        code, run, out = run_main("3/3", list(mutate_guard.MUTATIONS[:2]))
        self.assertEqual(code, 1, "the empty shard 3/3 exits %d, want 1: the run reads green with nothing tested" % code)
        self.assertFalse(run.called, "a mutant ran in an empty shard")
        self.assertIn("MUTATE_SHARD", out, "an empty shard prints no line that names MUTATE_SHARD")

    def test_the_anchor_check_reads_the_full_list_not_the_shard(self):
        real = mutate_guard.MUTATIONS
        stale = with_old(real[0], "NO SUCH ANCHOR TEXT ANYWHERE IN THE GUARD FAMILY")
        code, run, out = run_main("2/2", [stale, real[1], real[2]])
        self.assertEqual(code, 1)
        self.assertFalse(run.called, "a stale anchor outside the shard passed the pre-check")
        self.assertIn("stale mutation", out)

    def test_the_collision_check_reads_the_full_list_not_the_shard(self):
        real = mutate_guard.MUTATIONS
        code, run, out = run_main("2/2", [real[0], real[0]])
        self.assertEqual(code, 1)
        self.assertFalse(run.called, "two mutations share a path, and only the shard was checked for it")
        self.assertIn("share one path", out)


if __name__ == "__main__":
    unittest.main()
