#!/usr/bin/env python3
"""Cases for hooks/brief_rulings.py, the check that a finished lane brief keeps every owner ruling that governs its
step. Standard library only.

    python3 hooks/test_brief_rulings.py

The rulings are the store lint/ruled_store.py reads (roadmap/rulings on origin/roadmap). Each case builds its store
with the helpers of lint/test_ruled_store.py, imported as `fixture`, the one home of the store fixture. The model is a
stub: judge(brief, repo_dir, invoke=...) takes the call_judge seam's answer, a (dict, error) pair. A missing module
fails each case with one named assertion, never an import error. BRIEF_RULINGS_UNDER_TEST overrides the module path,
as a mutant run needs.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import test_ruled_store as fixture  # noqa: E402  the store fixture (lint/test_ruled_store.py)

MODULE = os.path.abspath(os.environ.get("BRIEF_RULINGS_UNDER_TEST") or os.path.join(HERE, "brief_rulings.py"))
STEP = "lane-brief-from-step"
OTHER_STEP = "some-other-step"
ACT_QUOTE = "a replaced PR closes when its replacer opens"
GUARD_RULING = "Guard reads apply to every lane, not only coordinators."
ALL_IDS = ["r-replace-close", "r-guard-lanes", "r-other"]
CLEAN_BRIEF = ("Lane brief: %s.\n\nReplaced PRs close when their replacer opens. Guard reads go to every lane.\n"
               % STEP)
DROP_BRIEF = ("Lane brief: %s.\n\nReplaced PRs close after the merge. Guard reads go to every lane.\n" % STEP)
NARROW_BRIEF = ("Lane brief: %s.\n\nReplaced PRs close when their replacer opens. Guard reads go to coordinators only.\n"
                % STEP)
OK_ANSWER = ({"ok": True, "reason": "both rulings are kept"}, None)


def store_entries():
    """Three rulings: two on STEP (one with a quote, one closed with none) and one on another step."""
    return {
        "r-replace-close": fixture.entry("r-replace-close", at="2026-11-09T21:27:00-06:00", step=STEP,
                                         quote=ACT_QUOTE,
                                         ruling="Replaced PRs close when their replacer opens, not after the merge.",
                                         status="open"),
        "r-guard-lanes": fixture.entry("r-guard-lanes", at="2026-11-10T09:00:00-06:00", step=STEP, quote=None,
                                       ruling=GUARD_RULING, status="closed"),
        "r-other": fixture.entry("r-other", at="2026-11-10T10:00:00-06:00", step=OTHER_STEP,
                                 quote="unrelated words", ruling="Unrelated ruling.", status="open"),
    }


def store_repo(testcase, entries=None):
    """A repo under this case's folder. `entries` is pointed at origin/roadmap; None gives a repo with no such ref."""
    root = tempfile.mkdtemp(prefix="brief_rulings_", dir=fixture.run_folder())
    testcase.addCleanup(shutil.rmtree, root, True)
    repo = fixture.init_repo(os.path.join(root, "repo"))
    if entries is not None:
        fixture.point_ref(repo, fixture.STORE_REF, fixture.ruling_files(entries), root)
    return repo


def assert_store_reads(testcase, repo, ids):
    """The scope check (P7): the store reads back with the fixture's ids before the subject is judged."""
    entries, state = fixture.ruled_store.read_store(repo)
    testcase.assertEqual(state, "ok", "scope: the fixture store does not read back")
    testcase.assertEqual(sorted(fixture.ids(entries)), sorted(ids), "scope: the fixture store holds other ids")


def brief_module(testcase):
    """The module under test, loaded by path. Absent or unloadable, the case fails by name."""
    if not os.path.isfile(MODULE):
        testcase.fail("hooks/brief_rulings.py is missing: no module judges the brief")
    spec = importlib.util.spec_from_file_location("brief_rulings", MODULE)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        testcase.fail("hooks/brief_rulings.py does not load: %s" % exc)
    return module


def member(testcase, module, name):
    if not hasattr(module, name):
        testcase.fail("hooks/brief_rulings.py has no %s()" % name)
    return getattr(module, name)


class Stub:
    """The model seam. Records each prompt and returns the canned (dict, error) pair."""

    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def __call__(self, *args, **kwargs):
        self.prompts.append(args[0] if args else kwargs.get("prompt"))
        return self.answer


def run_judge(testcase, brief, repo, answer):
    judge = member(testcase, brief_module(testcase), "judge")
    stub = Stub(answer)
    verdict, why = judge(brief, repo, invoke=stub)
    return verdict, why, stub


def listing(folder):
    return sorted((root, sorted(files), sorted(dirs)) for root, dirs, files in os.walk(folder))


def argv_of(args):
    return args if isinstance(args, (list, tuple)) else [args]


class ControlTests(unittest.TestCase):
    def test_control_the_fixture_store_reads_back_with_its_ids(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)


class StepOfTests(unittest.TestCase):
    def test_lane_brief_line_first_gives_its_slug(self):
        step_of = member(self, brief_module(self), "step_of")
        self.assertEqual(step_of("Lane brief: %s.\nbody" % STEP), STEP, "step_of: the Lane brief line's slug")

    def test_lane_brief_line_after_a_grant_line_gives_its_slug(self):
        step_of = member(self, brief_module(self), "step_of")
        self.assertEqual(step_of("Grant: owner 2026-11-09 21:27 CST, this lane.\nLane brief: %s.\nbody" % STEP),
                         STEP, "step_of: the Lane brief line after a leading Grant line")

    def test_a_cs_step_tag_in_the_text_gives_its_slug(self):
        step_of = member(self, brief_module(self), "step_of")
        self.assertEqual(step_of("Work on cs-step:%s in this lane.\nbody" % STEP), STEP,
                         "step_of: the cs-step tag")

    def test_a_lane_brief_line_below_prose_names_no_step(self):
        step_of = member(self, brief_module(self), "step_of")
        self.assertIsNone(step_of("Intro line.\nLane brief: %s.\nbody" % STEP),
                          "step_of: a Lane brief line that is not first names no step")

    def test_no_step_gives_none(self):
        step_of = member(self, brief_module(self), "step_of")
        self.assertIsNone(step_of("Just a brief with nothing that names a step."), "step_of: no step is None")


class GoverningTests(unittest.TestCase):
    def test_every_entry_of_the_step_is_listed_open_or_closed(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        governing = member(self, brief_module(self), "governing")
        lines, unknown = governing(CLEAN_BRIEF, repo)
        self.assertEqual(unknown, [], "governing: a readable store is not unknown")
        listed = sorted(line.split(":", 2)[1] for line in lines)
        self.assertEqual(listed, ["r-guard-lanes", "r-replace-close"],
                         "governing: the open and the closed entry of the step, and not the other step")

    def test_quote_is_preferred_over_ruling(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        governing = member(self, brief_module(self), "governing")
        lines, _unknown = governing(CLEAN_BRIEF, repo)
        self.assertIn("ruled:r-replace-close: %s (owner 2026-11-09T21:27:00-06:00)" % ACT_QUOTE, lines,
                      "governing: an entry with a quote shows the quote")

    def test_an_entry_with_no_quote_is_marked_as_a_paraphrase(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        governing = member(self, brief_module(self), "governing")
        lines, _unknown = governing(CLEAN_BRIEF, repo)
        self.assertIn("ruled:r-guard-lanes: (paraphrase) %s (owner 2026-11-10T09:00:00-06:00)" % GUARD_RULING, lines,
                      "governing: an entry with no quote shows the ruling marked (paraphrase)")

    def test_a_step_with_no_entries_gives_no_lines_and_no_unknown(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        governing = member(self, brief_module(self), "governing")
        lines, unknown = governing("Lane brief: step-with-no-rulings.\nbody", repo)
        self.assertEqual(lines, [], "governing: a step with no entry has no lines")
        self.assertEqual(unknown, [], "governing: a readable store with no entry for the step is not unknown")

    def test_an_absent_store_is_unknown_and_named_absent(self):
        repo = store_repo(self)
        governing = member(self, brief_module(self), "governing")
        lines, unknown = governing(CLEAN_BRIEF, repo)
        self.assertEqual(lines, [], "governing: an absent store gives no lines")
        self.assertTrue(any("absent" in item for item in unknown), "governing: unknown names the store as absent")

    def test_a_full_size_store_lists_every_entry_of_the_step(self):
        entries = {"r-full-%02d" % n: fixture.entry("r-full-%02d" % n, step=STEP, quote="quote %d" % n,
                                                    ruling="Ruling %d." % n)
                   for n in range(40)}
        repo = store_repo(self, entries)
        assert_store_reads(self, repo, list(entries))
        governing = member(self, brief_module(self), "governing")
        lines, _unknown = governing(CLEAN_BRIEF, repo)
        self.assertEqual(len(lines), 40, "governing: a full store lists all 40 entries of the step")


class PromptTests(unittest.TestCase):
    def test_prompt_holds_each_quote_verbatim_the_brief_and_the_shown_id(self):
        prompt = member(self, brief_module(self), "prompt")
        lines = ["ruled:r-replace-close: %s (owner 2026-11-09T21:27:00-06:00)" % ACT_QUOTE]
        text = prompt(DROP_BRIEF, lines, [])
        self.assertIn(ACT_QUOTE, text, "prompt: the ruling's quote, verbatim")
        self.assertIn(DROP_BRIEF, text, "prompt: the brief, verbatim")
        self.assertIn("ruled:r-replace-close", text, "prompt: the id the reason must name")

    def test_prompt_asks_for_an_ok_and_a_reason(self):
        prompt = member(self, brief_module(self), "prompt")
        text = prompt(DROP_BRIEF, ["ruled:r-replace-close: %s" % ACT_QUOTE], [])
        self.assertIn('"ok"', text, "prompt: the answer holds an ok key")
        self.assertIn('"reason"', text, "prompt: the answer holds a reason key")


class JudgeTests(unittest.TestCase):
    def test_a_brief_that_drops_a_ruling_is_flagged_and_its_id_is_in_why(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        answer = ({"ok": False, "reason": "ruled:r-replace-close is dropped: the brief closes after the merge."}, None)
        verdict, why, stub = run_judge(self, DROP_BRIEF, repo, answer)
        self.assertEqual(len(stub.prompts), 1, "model calls: one call for a brief with a governing ruling")
        self.assertIn(ACT_QUOTE, stub.prompts[0], "prompt: the dropped ruling's quote is shown")
        self.assertEqual(verdict, "flag", "verdict: a brief that drops a shown ruling is flagged")
        self.assertIn("r-replace-close", why, "why: names the id the reason cites")

    def test_a_brief_that_narrows_a_ruling_is_flagged_and_its_id_is_in_why(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        answer = ({"ok": False, "reason": "ruled:r-guard-lanes is narrowed to coordinators only."}, None)
        verdict, why, stub = run_judge(self, NARROW_BRIEF, repo, answer)
        self.assertEqual(len(stub.prompts), 1, "model calls: one call for a brief with a governing ruling")
        self.assertIn(GUARD_RULING, stub.prompts[0], "prompt: the narrowed ruling's words are shown")
        self.assertEqual(verdict, "flag", "verdict: a brief that narrows a shown ruling is flagged")
        self.assertIn("r-guard-lanes", why, "why: names the id the reason cites")

    def test_a_clean_brief_is_ok(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        verdict, _why, stub = run_judge(self, CLEAN_BRIEF, repo, OK_ANSWER)
        self.assertEqual(len(stub.prompts), 1, "model calls: one call for a brief with a governing ruling")
        self.assertEqual(verdict, "ok", "verdict: a brief that keeps every ruling is ok")

    def test_a_reason_that_cites_no_shown_id_is_unvetted_never_flagged(self):
        cases = (
            ("a made-up id", "ruled:r-invented drops the act."),
            ("a real id that was not shown, and a shown one", "ruled:r-replace-close is dropped, and ruled:r-other "
                                                              "conflicts."),
            ("no id at all", "The brief drops the act."),
        )
        for label, reason in cases:
            with self.subTest(label=label):
                repo = store_repo(self, store_entries())
                assert_store_reads(self, repo, ALL_IDS)
                verdict, _why, _stub = run_judge(self, DROP_BRIEF, repo, ({"ok": False, "reason": reason}, None))
                self.assertEqual(verdict, "unvetted", "verdict: a reason that cites no shown id is unvetted")

    def test_a_store_git_cannot_read_is_unvetted_and_names_the_store(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        real = subprocess.Popen

        def no_git(args, *rest, **kwargs):
            if os.path.basename(str(argv_of(args)[0])) == "git":
                raise OSError("git cannot start (test)")
            return real(args, *rest, **kwargs)

        with mock.patch.object(subprocess, "Popen", new=no_git):
            verdict, why, _stub = run_judge(self, CLEAN_BRIEF, repo, OK_ANSWER)
        self.assertEqual(verdict, "unvetted", "verdict: a store git cannot read is unvetted, never ok")
        self.assertIn(fixture.ruled_store.STORE_REF, why, "why: names the store that could not be read")

    def test_an_absent_store_is_unvetted_and_says_absent(self):
        repo = store_repo(self)
        verdict, why, _stub = run_judge(self, CLEAN_BRIEF, repo, OK_ANSWER)
        self.assertEqual(verdict, "unvetted", "verdict: an absent store is unvetted, never ok")
        self.assertIn("absent", why, "why: says the store is absent")

    def test_a_brief_with_no_step_is_skipped_with_no_model_call(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        verdict, _why, stub = run_judge(self, "Just a brief, no step named.\n", repo, OK_ANSWER)
        self.assertEqual(verdict, "skipped", "verdict: a brief with no step is skipped")
        self.assertEqual(stub.prompts, [], "model calls: none for a brief with no step")

    def test_a_step_with_no_governing_rulings_is_skipped_with_no_model_call(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        verdict, _why, stub = run_judge(self, "Lane brief: step-with-no-rulings.\nbody", repo, OK_ANSWER)
        self.assertEqual(verdict, "skipped", "verdict: a step with no governing ruling is skipped")
        self.assertEqual(stub.prompts, [], "model calls: none for a step with no governing ruling")

    def test_a_model_error_or_timeout_is_unvetted_never_ok(self):
        for error in ("claude exited 1", "timeout after 60 s"):
            with self.subTest(error=error):
                repo = store_repo(self, store_entries())
                assert_store_reads(self, repo, ALL_IDS)
                verdict, _why, stub = run_judge(self, CLEAN_BRIEF, repo, (None, error))
                self.assertEqual(len(stub.prompts), 1, "model calls: the one call that failed")
                self.assertEqual(verdict, "unvetted", "verdict: a model error or timeout is unvetted")

    def test_judging_starts_one_model_call_and_at_most_two_git_processes(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        judge = member(self, brief_module(self), "judge")
        real = subprocess.Popen
        starts = []

        class CountingPopen(real):
            def __init__(self, args, *rest, **kwargs):
                starts.append(argv_of(args))
                super().__init__(args, *rest, **kwargs)

        # ruled_store.ruled_entries starts two git processes (an ls-tree and a cat-file --batch). The entries here
        # name no lands_in, so no third one starts (lint/ruled_store.py, the module docstring's cost line).
        before = listing(os.path.dirname(repo))
        stub = Stub(OK_ANSWER)
        with mock.patch.object(subprocess, "Popen", new=CountingPopen):
            judge(CLEAN_BRIEF, repo, invoke=stub)
        self.assertEqual(len(stub.prompts), 1, "model calls: judging starts exactly one")
        self.assertLessEqual(len(starts), 2, "subprocess starts: at most the two git reads the store documents")
        self.assertTrue(all(os.path.basename(str(argv[0])) == "git" for argv in starts),
                        "subprocess starts: each is a git read")
        self.assertEqual(listing(os.path.dirname(repo)), before, "files: judging writes no file")


class MarkdownLeadStepTests(unittest.TestCase):
    """A brief may open with markdown (a heading, a bold label, a quote), as guard_merge reads it. Each form is read
    first, and after a leading Grant line."""
    GRANT = "Grant: owner 2026-11-09 21:27 CST, this lane.\n"

    def check_form(self, form, name):
        step_of = member(self, brief_module(self), "step_of")
        for label, text in (("first line", form + "\nbody"), ("after a Grant line", self.GRANT + form + "\nbody")):
            with self.subTest(label=label):
                self.assertEqual(step_of(text), STEP, "step_of: a %s Lane brief line gives no slug" % name)

    def test_a_heading_led_lane_brief_gives_its_slug(self):
        self.check_form("# Lane brief: %s. Topic: lane-topic." % STEP, "heading-led")

    def test_a_bold_label_lane_brief_gives_its_slug(self):
        self.check_form("**Lane brief:** %s. Topic: lane-topic." % STEP, "bold-label")

    def test_a_quoted_lane_brief_gives_its_slug(self):
        self.check_form("> Lane brief: %s. Topic: lane-topic." % STEP, "quoted")


class MarkdownLeadJudgeTests(unittest.TestCase):
    def test_a_markdown_led_brief_that_drops_a_ruling_reaches_the_model(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        brief = ("# Lane brief: %s. Topic: lane-topic.\n\nReplaced PRs close after the merge. "
                 "Guard reads go to every lane.\n" % STEP)
        answer = ({"ok": False, "reason": "ruled:r-replace-close is dropped: the brief closes after the merge."}, None)
        verdict, _why, stub = run_judge(self, brief, repo, answer)
        self.assertEqual(len(stub.prompts), 1, "model calls: a markdown-led brief with a governing ruling is judged once")
        self.assertEqual(verdict, "flag", "verdict: a markdown-led brief that drops a shown ruling is flagged")


def run_cli(testcase, argv):
    """The module run as a script, the way a session runs it: the real exit code, stdout and stderr."""
    if not os.path.isfile(MODULE):
        testcase.fail("hooks/brief_rulings.py is missing: no module judges the brief")
    return subprocess.run([sys.executable, MODULE] + argv, capture_output=True, text=True, timeout=60)


def run_main(testcase, argv, answer=OK_ANSWER):
    """main(argv) in this process, with the model seam (call_judge.invoke_model, which judge() calls by name) replaced
    by a stub. Returns (exit code, stdout, stub)."""
    main = member(testcase, brief_module(testcase), "main")
    import call_judge
    stub = Stub(answer)
    out = io.StringIO()
    with mock.patch.object(call_judge, "invoke_model", stub), contextlib.redirect_stdout(out):
        try:
            code = main(argv)
        except BaseException as exc:
            testcase.fail("main raised %s: it must return an exit code and a verdict line" % type(exc).__name__)
    return code, out.getvalue(), stub


def brief_file(repo, text):
    path = os.path.join(os.path.dirname(repo), "brief.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class MainTests(unittest.TestCase):
    def assert_one_unvetted_line(self, done):
        self.assertNotIn("Traceback", done.stderr, "traceback: an unreadable brief is a verdict, not a crash")
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), 1, "stdout: one verdict line")
        self.assertTrue(lines[0].startswith("unvetted: "), "stdout: the verdict line is unvetted")

    def test_a_missing_brief_file_exits_2_with_one_unvetted_line(self):
        repo = store_repo(self, store_entries())
        missing = os.path.join(os.path.dirname(repo), "no-such-brief.md")
        done = run_cli(self, [missing, "--repo", repo])
        self.assertEqual(done.returncode, 2, "exit code: a missing BRIEF_FILE exits 2")
        self.assert_one_unvetted_line(done)

    def test_an_unreadable_brief_file_exits_2_with_one_unvetted_line(self):
        repo = store_repo(self, store_entries())
        folder = os.path.join(os.path.dirname(repo), "a-folder")
        os.mkdir(folder)
        not_utf8 = os.path.join(os.path.dirname(repo), "not-utf8.md")
        with open(not_utf8, "wb") as handle:
            handle.write(b"\xff\xfe\x00 Lane brief: x.\n")
        for label, path in (("a folder", folder), ("bytes that are not UTF-8", not_utf8)):
            with self.subTest(label=label):
                done = run_cli(self, [path, "--repo", repo])
                self.assertEqual(done.returncode, 2, "exit code: an unreadable BRIEF_FILE exits 2")
                self.assert_one_unvetted_line(done)

    def test_a_flag_exits_1_and_prints_the_reason(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        path = brief_file(repo, DROP_BRIEF)
        answer = ({"ok": False, "reason": "ruled:r-replace-close is dropped: the brief closes after the merge."}, None)
        code, out, _stub = run_main(self, [path, "--repo", repo], answer)
        self.assertEqual(code, 1, "exit code: a flag exits 1")
        self.assertTrue(out.startswith("flag: "), "stdout: the verdict line is flag")
        self.assertIn("ruled:r-replace-close", out, "stdout: the reason names the shown id")

    def test_an_ok_exits_0(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        code, out, _stub = run_main(self, [brief_file(repo, CLEAN_BRIEF), "--repo", repo], OK_ANSWER)
        self.assertEqual(code, 0, "exit code: ok exits 0")
        self.assertTrue(out.startswith("ok: "), "stdout: the verdict line is ok")

    def test_a_skipped_brief_exits_0_with_no_model_call(self):
        repo = store_repo(self, store_entries())
        assert_store_reads(self, repo, ALL_IDS)
        code, out, stub = run_main(self, [brief_file(repo, "Just a brief, no step named.\n"), "--repo", repo])
        self.assertEqual(code, 0, "exit code: skipped exits 0")
        self.assertTrue(out.startswith("skipped: "), "stdout: the verdict line is skipped")
        self.assertEqual(stub.prompts, [], "model calls: none for a brief with no step")


def tearDownModule():
    shutil.rmtree(fixture.run_folder(), ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
