#!/usr/bin/env python3
"""Cases for the readers of origin/roadmap that fetch a stale ref before they judge: hooks/sendmessage_state.py
(the past-ruling check, read_rulings), hooks/override.py (the Opus step grant, take) and hooks/question_form.py
(the roadmap steps, _read_steps; the ruled store of each root, past_rulings). Standard library only.

    python3 hooks/test_roadmap_readers.py

Each reader calls roadmap_ref.fresh_ref once per read. A ruling or a step that exists only on origin is found once the
ref is fetched, and a failed fetch says "read as of" where the reader's verdict can carry it. The fixtures are the
store fixtures of lint/test_ruled_store.py, one home for the roadmap refs. No network: every origin is a local path.
"""
import contextlib
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import test_ruled_store as fixture  # noqa: E402  the one home of the roadmap-ref fixtures
import override  # noqa: E402
import question_form  # noqa: E402
import sendmessage_state  # noqa: E402

OLD_DECISION = "old-decision"  # a bare decision slug: a ruling that names it supersedes the whole decision
RULING = "r-old"
MESSAGE = "The owner settled it: decisions/%s covers this, so the old rule stands." % OLD_DECISION
EMPTY = fixture.ruling_files({"r-other": fixture.entry("r-other")})
SUPERSEDING = fixture.ruling_files({RULING: fixture.entry(RULING, supersedes=[{"kind": "decision",
                                                                               "ref": OLD_DECISION}])})
SESSION = "sess-step-grant"  # a lane's session id: a step names it in its `lane` field
ROLE = "builder"
STEP_FILE = "roadmap/data/steps/lane-grant.json"
GRANT_STEP = {STEP_FILE: json.dumps({
    "id": "lane-grant", "lane": SESSION, "status": "todo",
    "grants": [{"role": None, "by": "triage", "words": "Opus spawn ok on this lane", "at": "2026-11-13T12:00:00-06:00"}],
}, indent=2)}
NOTE_STEP = {"roadmap/data/steps/origin-only-step.json": json.dumps(
    {"note": "Opus spawn on the lane is granted", "why": "owner ruling"}, indent=2)}


def merged(*parts):
    """One store tree from several {path: text} parts; later parts win."""
    tree = {}
    for part in parts:
        tree.update(part)
    return tree


def fresh_helper(fake):
    """A mock of roadmap_ref whose fresh_ref answers ""."""
    fake.fresh_ref.return_value = ""
    return fake


class RulingsReadTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="roadmap_readers_", dir=fixture.run_folder())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_the_ruling_check_calls_fresh_ref_once_per_read(self):
        repo = fixture.clone_with_origin(self.root, "once", None, EMPTY)
        helper = fresh_helper(mock.Mock())
        with mock.patch.dict(sys.modules, {"roadmap_ref": helper}):
            sys.modules.pop("sendmessage_state", None)
            importlib.import_module("sendmessage_state").read_rulings(repo)
        self.assertEqual(helper.fresh_ref.call_count, 1, "the ruling read called fresh_ref %d times, want 1"
                         % helper.fresh_ref.call_count)

    def test_a_ruling_only_on_origin_is_read_after_a_stale_fetch(self):
        origin = fixture.bare_origin(self.root, "ruling-origin", EMPTY)
        repo = fixture.clone_with_origin(self.root, "ruling-stale", origin, EMPTY)
        fixture.point_ref(origin, "refs/heads/roadmap", SUPERSEDING, self.root)
        fixture.without_fetch_head(repo)
        hit = sendmessage_state.past_ruling_hit({"cwd": repo}, MESSAGE)
        self.assertEqual(hit, (OLD_DECISION, RULING), "a ruling only on origin, behind a stale ref, was not read: %r"
                         % (hit,))

    def test_a_pass_after_a_failed_fetch_says_read_as_of(self):
        gone = os.path.join(self.root, "gone-pass.git")
        repo = fixture.clone_with_origin(self.root, "pass", gone, EMPTY)
        fixture.without_fetch_head(repo)
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            hit = sendmessage_state.past_ruling_hit({"cwd": repo}, MESSAGE)
        self.assertIsNone(hit, "control: a store with no superseding ruling gave a hit: %r" % (hit,))
        self.assertIn("read as of", said.getvalue(), "the pass said nothing about a fetch that failed: %r"
                      % said.getvalue())

    def test_a_refusal_after_a_failed_fetch_says_read_as_of(self):
        gone = os.path.join(self.root, "gone-refuse.git")
        repo = fixture.clone_with_origin(self.root, "refuse", gone, SUPERSEDING)
        fixture.without_fetch_head(repo)
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            hit = sendmessage_state.past_ruling_hit({"cwd": repo}, MESSAGE)
        self.assertEqual(hit, (OLD_DECISION, RULING), "control: the local superseding ruling was not found: %r" % (hit,))
        self.assertIn("read as of", said.getvalue(), "the refusal's read said nothing about a fetch that failed: %r"
                      % said.getvalue())

    def test_the_second_root_checks_its_own_roadmap_ref(self):
        # past_rulings reads the ruled store of each root, in order. The first root has no store, so the read reaches
        # the second root, and that root's own roadmap ref is freshness-checked.
        first = fixture.init_repo(os.path.join(self.root, "second-root-first"))
        second = fixture.clone_with_origin(self.root, "second-root-settings", None,
                                           fixture.ruling_files({RULING: fixture.entry(RULING)}))
        helper = fresh_helper(mock.Mock())
        with mock.patch("guard_pointer.pointer_checkout", return_value=second), \
                mock.patch.dict(sys.modules, {"roadmap_ref": helper}):
            candidates, _unknown = question_form.past_rulings("Should we keep the store to one place?", first)
        checked = [os.path.realpath(call.args[0]) for call in helper.fresh_ref.call_args_list]
        self.assertIn(os.path.realpath(first), checked, "control: the first root's roadmap ref was not checked: %r"
                      % (checked,))
        self.assertTrue(any(c.startswith("ruled:%s:" % RULING) for c in candidates),
                        "the second root's ruling is not a candidate, so the read did not reach that root: %r"
                        % (candidates,))
        self.assertIn(os.path.realpath(second), checked, "the second root's roadmap ref was not checked: %r"
                      % (checked,))


class StepGrantTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="roadmap_grant_", dir=fixture.run_folder())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_step_grant_only_on_origin_is_found_after_a_stale_fetch(self):
        origin = fixture.bare_origin(self.root, "grant-origin", EMPTY)
        repo = fixture.clone_with_origin(self.root, "grant-stale", origin, EMPTY)
        fixture.point_ref(origin, "refs/heads/roadmap", merged(EMPTY, GRANT_STEP), self.root)
        fixture.without_fetch_head(repo)
        with mock.patch.dict(os.environ):
            os.environ.pop(override.LANE_ENV, None)
            verdict = override.take(SESSION, "agent-1", override.now(), rule=override.OPUS_RULE, spawn_role=ROLE,
                                    cwd=repo)
        self.assertEqual(verdict, override.STEP_LIFTED, "a step grant only on origin, behind a stale ref, did not lift:"
                         " %r" % (verdict,))

    def test_a_failed_fetch_of_the_step_grant_says_read_as_of_in_the_guard_log(self):
        import guard_core  # the guard's log writer; the record is patched, nothing is written
        gone = os.path.join(self.root, "gone-grant.git")
        repo = fixture.clone_with_origin(self.root, "grant-fail", gone, EMPTY)
        fixture.without_fetch_head(repo)
        with mock.patch.object(guard_core, "record") as record, mock.patch.dict(os.environ):
            os.environ.pop(override.LANE_ENV, None)
            verdict = override.take(SESSION, "agent-1", override.now(), rule=override.OPUS_RULE, spawn_role=ROLE,
                                    cwd=repo)
        self.assertIsNone(verdict, "control: a store with no grant lifted the refusal: %r" % (verdict,))
        noted = any("read as of" in str(call) for call in record.call_args_list)
        self.assertTrue(noted, "the step read could not fetch the roadmap and logged nothing about it: %r"
                        % (record.call_args_list,))

    def test_the_step_read_calls_fresh_ref_once(self):
        repo = fixture.clone_with_origin(self.root, "grant-once", None, EMPTY)
        helper = fresh_helper(mock.Mock())
        with mock.patch.dict(sys.modules, {"roadmap_ref": helper}), mock.patch.dict(os.environ):
            sys.modules.pop("override", None)
            module = importlib.import_module("override")
            os.environ.pop(module.LANE_ENV, None)
            module.take(SESSION, "agent-1", module.now(), rule=module.OPUS_RULE, spawn_role=ROLE, cwd=repo)
        self.assertEqual(helper.fresh_ref.call_count, 1, "the step read called fresh_ref %d times, want 1"
                         % helper.fresh_ref.call_count)


class StepNoteTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="roadmap_steps_", dir=fixture.run_folder())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_the_steps_read_calls_fresh_ref_once(self):
        repo = fixture.clone_with_origin(self.root, "steps-once", None, EMPTY)
        helper = fresh_helper(mock.Mock())
        with mock.patch.dict(sys.modules, {"roadmap_ref": helper}):
            sys.modules.pop("question_form", None)
            importlib.import_module("question_form")._read_steps(repo)
        self.assertEqual(helper.fresh_ref.call_count, 1, "the steps read called fresh_ref %d times, want 1"
                         % helper.fresh_ref.call_count)

    def test_a_step_only_on_origin_is_read_after_a_stale_fetch(self):
        origin = fixture.bare_origin(self.root, "steps-origin", EMPTY)
        repo = fixture.clone_with_origin(self.root, "steps-stale", origin, EMPTY)
        fixture.point_ref(origin, "refs/heads/roadmap", merged(EMPTY, NOTE_STEP), self.root)
        fixture.without_fetch_head(repo)
        steps, state = question_form._read_steps(repo)
        self.assertIn("origin-only-step", steps, "a step only on origin, behind a stale ref, was not read: state %r"
                      % (state,))

    def test_a_failed_fetch_of_the_steps_says_read_as_of(self):
        gone = os.path.join(self.root, "gone-steps.git")
        repo = fixture.clone_with_origin(self.root, "steps-fail", gone, merged(EMPTY, NOTE_STEP))
        fixture.without_fetch_head(repo)
        steps, state = question_form._read_steps(repo)
        self.assertIn("origin-only-step", steps, "control: the local step was not read: state %r" % (state,))
        self.assertIn("read as of", repr((steps, state)), "the steps read said nothing about a fetch that failed: %r"
                      % ((steps, state),))


class SecondRootNoteTests(unittest.TestCase):
    """past_rulings reads the ruled store of the second root when the first has none. That read's freshness note goes
    into the verdict as the first root's does: a failed fetch on the second root is named, never dropped. The check is
    the real roadmap_ref.fresh_ref, not a mock."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="roadmap_second_", dir=fixture.run_folder())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_failed_fetch_on_the_second_root_is_named_in_the_verdict(self):
        gone = os.path.join(self.root, "gone-second-root.git")  # no repo there, so the fetch fails
        first = fixture.init_repo(os.path.join(self.root, "second-root-no-ref"))
        fixture.set_fetch_head(first)  # the first root reads fresh, so only the second root's fetch can say read as of
        second = fixture.clone_with_origin(self.root, "second-root-gone", gone,
                                           fixture.ruling_files({RULING: fixture.entry(RULING)}))
        fixture.without_fetch_head(second)
        with mock.patch("guard_pointer.pointer_checkout", return_value=second):
            candidates, unknown = question_form.past_rulings("Should we keep the store to one place?", first)
        verdict = "\n".join(candidates + unknown)
        self.assertTrue(any(c.startswith("ruled:%s:" % RULING) for c in candidates),
                        "control: the second root's ruling is not a candidate, so its store was not read: %r"
                        % (candidates,))
        self.assertIn("read as of", verdict, "a failed fetch of the second root's ruled store is not named in the "
                                             "verdict: %r" % (verdict,))


def tearDownModule():
    for folder in fixture._RUN:
        shutil.rmtree(folder, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=2)
