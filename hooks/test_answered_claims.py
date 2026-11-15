#!/usr/bin/env python3
"""Cases for the answered-claim check: a sent message that says a waiting-page item is answered, when the page's
data holds no owner answer for it, is refused.

Run it from the repository root:

    python3 hooks/test_answered_claims.py

Standard library only, and no test runner. The judge is hooks/answered_claims.py: answered_claim_hit(tool,
tool_input, cwd) returns (matched, reason) for a refused claim and None for everything else. Each case loads it
fresh from its file, so a missing file fails the case with its name, not at import.

Fixtures are throwaway git repos under this run's folder. Each holds the registry entry in
.claude/layout-extras.json and, on a record branch, the page's store: <export>/items/<id>.json and
<export>/answers/<id>.json, written as the export writes them (two-space indent). The record branch and the export
folder are not the defaults, so a hard-coded name fails. A fixture is built once per run and read by every case
that names it. The judge never writes to a fixture.

The guard-level case runs hooks/guard.py as a child, with one JSON payload on stdin as the harness sends it, and
reads the decision off stdout. Its refusals are logged to a folder of this run, never the real config folder.

The cost cases count child starts with testing/cost_probe.py: a message with no claim starts none, and a claim
starts at most two git reads.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "lint"))
sys.path.insert(0, os.path.join(ROOT, "testing"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import cost_probe  # noqa: E402  the shared child-start counter (testing/cost_probe.py)
import layout  # noqa: E402  the one home of the registry read (lint/layout.py), for the fixture's scope check

RUN_FOLDER = _test_temp.run_folder()
HELPER_REL = "hooks/answered_claims.py"
HELPER = os.path.join(HERE, "answered_claims.py")
GUARD = os.path.join(HERE, "guard.py")
RULE = "brief-checks-answered-claims-match-page"
TOOL = "mcp__claude-code-remote__send_message"
CREATE_TOOL = "mcp__claude-code-remote__create_session"
SESSION = "session_fixture0001"
RECORD_BRANCH = "page-records"  # not the default record branch, so a hard-coded default fails the cases
EXPORT = "waiting"  # the registry entry's export folder, not the default one
PAGE_URL = "https://claude.ai/artifact/fixture-page"
AT = "2026-11-14T10:00:00-06:00"
HANG_GUARD = 300  # seconds a child may run: a hang guard for a stuck child, never a timing check
EXTRAS = {
    "kinds": {},
    "record-branch": RECORD_BRANCH,
    "artifacts": [{"id": "fixture-page", "url": PAGE_URL, "role": "waiting-page",
                   "account": "fixture", "export": EXPORT}],
}
CLAIM = "item 874 is already answered."
NO_CLAIM = "item 874 is open and waits on the owner."
SHARED = {}


def git_env():
    """The runner's environment without any GIT_ variable, which would point git at another repo."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
    return env


GIT_ENV = git_env()


def git(repo, *args):
    """Runs git in a fixture repo and returns its stdout. A failed fixture step raises, with git's own text."""
    done = subprocess.run(["git", "-C", repo, "-c", "commit.gpgsign=false", *args], capture_output=True,
                          text=True, env=GIT_ENV, timeout=HANG_GUARD)
    if done.returncode:
        raise RuntimeError("fixture step `git %s` failed: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout


def ref_holds(repo, ref, path):
    """True when `ref` holds a file at `path`."""
    done = subprocess.run(["git", "-C", repo, "cat-file", "-e", "%s:%s" % (ref, path)], capture_output=True,
                          text=True, env=GIT_ENV, timeout=HANG_GUARD)
    return done.returncode == 0


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_json(path, value):
    """JSON as the export writes it: two-space indent, so each top-level key sits on its own line."""
    write_text(path, json.dumps(value, indent=2) + "\n")


def new_folder(label):
    return tempfile.mkdtemp(prefix=label + "-", dir=RUN_FOLDER)


def item(n, answered=False):
    """One item row: its id and number, and a lastAnswer when the owner answered in chat."""
    row = {"id": "item-%d" % n, "n": n}
    if answered:
        row["lastAnswer"] = {"at": AT, "choice": "a"}
    return row


def answer(n):
    """One answers file: the item it answers, its number and the time. The id names the file only."""
    return {"id": "answer-%d" % n, "item": "item-%d" % n, "n": n, "at": AT}


def write_store(folder, items=(), answers=()):
    for name in ("items", "answers"):
        write_text(os.path.join(folder, EXPORT, name, ".gitkeep"), "")  # keeps an empty folder in git
    for row in items:
        write_json(os.path.join(folder, EXPORT, "items", row["id"] + ".json"), row)
    for row in answers:
        body = {key: value for key, value in row.items() if key != "id"}
        write_json(os.path.join(folder, EXPORT, "answers", row["id"] + ".json"), body)


def make_store(folder, items=(), answers=(), origin_answers=(), extras=True, record=True):
    """A fixture repo. The default branch holds the registry entry. The record branch holds the store. Each
    origin answer is committed only on refs/remotes/origin/<record branch>, so the local record branch lacks it."""
    os.makedirs(folder)
    git(folder, "init", "-q")
    if extras:
        write_json(os.path.join(folder, ".claude", "layout-extras.json"), EXTRAS)
    write_text(os.path.join(folder, "README.md"), "fixture\n")
    git(folder, "add", "-A")
    git(folder, "commit", "-q", "-m", "fixture: default branch")
    default = git(folder, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if record:
        git(folder, "checkout", "-q", "-b", RECORD_BRANCH)
        write_store(folder, items, answers)
        git(folder, "add", "-A")
        git(folder, "commit", "-q", "-m", "fixture: record branch")
        if origin_answers:
            git(folder, "checkout", "-q", "-b", "fixture-origin")
            write_store(folder, (), origin_answers)
            git(folder, "add", "-A")
            git(folder, "commit", "-q", "-m", "fixture: origin answers")
            git(folder, "update-ref", "refs/remotes/origin/" + RECORD_BRANCH, "HEAD")
            git(folder, "checkout", "-q", RECORD_BRANCH)
            git(folder, "branch", "-q", "-D", "fixture-origin")
    git(folder, "checkout", "-q", default)
    return folder


def shared(label, **kwargs):
    """A fixture repo built once per run, under its own folder of this run."""
    if label not in SHARED:
        SHARED[label] = make_store(os.path.join(new_folder(label), "repo"), **kwargs)
    return SHARED[label]


def refusing():
    """The store every refusal case reads: items 131, 806 and 874 exist and hold no owner answer."""
    return shared("refusing", items=[item(131), item(806), item(874)])


def load_helper(case):
    """The judge module, loaded fresh from its file. A missing file or a missing function fails the case, named."""
    case.assertTrue(os.path.isfile(HELPER), "%s is missing: no judge of an answered claim exists" % HELPER_REL)
    spec = importlib.util.spec_from_file_location("answered_claims_case", HELPER)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        case.fail("%s does not load: %r" % (HELPER_REL, error))
    case.assertTrue(callable(getattr(module, "answered_claim_hit", None)),
                    "%s has no function answered_claim_hit()" % HELPER_REL)
    return module


def judge(case, tool, tool_input, repo):
    return load_helper(case).answered_claim_hit(tool, tool_input, repo)


def send(case, message, repo):
    return judge(case, TOOL, {"session_id": SESSION, "message": message}, repo)


def judge_quiet(case, tool, tool_input, repo):
    """The judged result, and the stderr lines the judge wrote while it ran."""
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        result = judge(case, tool, tool_input, repo)
    return result, [line for line in buffer.getvalue().splitlines() if line.strip()]


def core(sentence):
    return sentence.strip().rstrip(".?!")


def assert_refused(case, result, item_number, sentence, echo=True):
    """A refusal is a (matched, reason) pair whose reason names the item number and, unless `echo` is False, the
    sentence. The judge reads a sentence with its code span blanked and its line breaks joined, so a case whose
    sentence holds either one passes echo=False."""
    case.assertIsNotNone(result, "'%s' was allowed: a refusal naming item %s was expected"
                         % (core(sentence), item_number))
    case.assertIsInstance(result, tuple, "answered_claim_hit() returned %r, not a (matched, reason) pair" % (result,))
    case.assertEqual(len(result), 2, "answered_claim_hit() returned %d values, not 2" % len(result))
    reason = result[1]
    case.assertIsInstance(reason, str, "the refusal's reason is %r, not text" % (reason,))
    case.assertIn(item_number, reason, "the refusal for '%s' does not name item %s: %r"
                  % (core(sentence), item_number, reason[:160]))
    if echo:
        case.assertIn(core(sentence), reason, "the refusal for item %s does not name the sentence '%s'"
                      % (item_number, core(sentence)))


def assert_allowed(case, result, sentence):
    case.assertIsNone(result, "'%s' was refused, and a message that does not claim an answer must pass: %r"
                      % (core(sentence), str(result)[:160]))


def assert_fail_open(case, result, stderr, sentence):
    """An allow that the judge could not check: no refusal, and one stderr line that says so."""
    assert_allowed(case, result, sentence)
    case.assertEqual(len(stderr), 1, "a fail-open allow of '%s' wrote %d stderr lines, not 1: %r"
                     % (core(sentence), len(stderr), stderr[:2]))


def run_guard(repo, message):
    """hooks/guard.py run as the harness runs it: one JSON payload on stdin, the decision on stdout. The
    environment is the runner's minus every variable the guard reads, and its log goes to a folder of this run."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": TOOL,
               "tool_input": {"session_id": SESSION, "message": message},
               "session_id": "fixture-session-01", "cwd": repo}
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("CLAUDE", "GIT_", "LOCAL_TIME", "GUARD_"))}
    config = os.path.join(RUN_FOLDER, "config")
    os.makedirs(config, exist_ok=True)
    env["CLAUDE_CONFIG_DIR"] = config
    return subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
                          env=env, cwd=repo, timeout=HANG_GUARD)


def guard_decision(case, done):
    """The hookSpecificOutput of a refusal, or None for an allow (an empty stdout)."""
    case.assertEqual(done.returncode, 0, "guard.py exited %d: %s" % (done.returncode, done.stderr.strip()[-200:]))
    text = done.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        case.fail("guard.py printed text that is not a decision: %r" % text[:200])


class FixtureTests(unittest.TestCase):
    """The fixture is what the refusal cases say it is. These pass on any tree, and a fixture fault fails here first."""

    def test_the_registry_reads_the_export_folder_of_a_waiting_page(self):
        repo = refusing()
        entries = layout.artifacts(repo)
        self.assertEqual(len(entries), 1, "the fixture registry holds %d artifact entries, not 1" % len(entries))
        self.assertEqual(entries[0]["role"], layout.WAITING_ROLE, "the fixture entry is not the waiting page")
        self.assertEqual(entries[0]["export"], EXPORT, "the fixture entry exports to %r, not %r"
                         % (entries[0]["export"], EXPORT))
        self.assertEqual(layout.record_branch(repo), RECORD_BRANCH, "the fixture names another record branch")

    def test_the_store_holds_item_874_with_no_answer_on_the_record_branch(self):
        repo = refusing()
        ref = "refs/heads/" + RECORD_BRANCH
        self.assertTrue(ref_holds(repo, ref, EXPORT + "/items/item-874.json"),
                        "the record branch holds no item 874 file")
        self.assertFalse(ref_holds(repo, ref, EXPORT + "/answers/answer-874.json"),
                         "the record branch already holds an answer to item 874")


class PassTests(unittest.TestCase):
    def test_a_negated_claim_passes(self):
        repo = refusing()
        # Scope first: the same item, unnegated, is refused on this store, so a pass below is the text test's doing.
        assert_refused(self, send(self, CLAIM, repo), "874", CLAIM)
        for sentence in (
                "item 874 is recommended, not answered.",
                "item 874 is not yet answered.",
                "item 874 is unanswered.",
                "item 874 wasn't answered by the owner.",
                "item 874 was never answered.",
                "item 874 cannot be answered yet.",
                "item 874 is yet to be answered."):
            with self.subTest(sentence=sentence):
                assert_allowed(self, send(self, sentence, repo), sentence)

    def test_a_longer_word_or_a_hyphen_joined_word_passes(self):
        repo = refusing()
        for sentence in ("item 874 was overruled by the coordinator.",
                         "item 874 is answered-needs-source."):
            with self.subTest(sentence=sentence):
                assert_allowed(self, send(self, sentence, repo), sentence)

    def test_a_question_claims_nothing(self):
        assert_allowed(self, send(self, "is item 874 already answered?", refusing()), "is item 874 already answered?")

    def test_a_claim_with_no_item_reference_passes(self):
        repo = refusing()
        for sentence in ("PR #3506 approved.", "The owner ruled on the PR."):
            with self.subTest(sentence=sentence):
                assert_allowed(self, send(self, sentence, repo), sentence)

    def test_a_claim_inside_inline_code_or_a_fence_passes(self):
        repo = refusing()
        for message in ("The page reads `item 874 is already answered` from the record.",
                        "```\nitem 874 is already answered.\n```"):
            with self.subTest(message=message):
                assert_allowed(self, send(self, message, repo), message)

    def test_the_remedy_sentence_with_an_item_passes(self):
        sentence = "item 874 needs the owner's answer: cite it, or say \"recommended, not answered\"."
        assert_allowed(self, send(self, sentence, refusing()), sentence)

    def test_the_remedy_citing_the_owner_answer_and_its_time_passes(self):
        # The refusal's own remedy: an owner answer cited with its time is the answer the page does not hold.
        repo = refusing()
        assert_refused(self, send(self, "Item 874 is answered.", repo), "874", "Item 874 is answered.")  # scope
        sentence = "Item 874 (owner, 2026-11-15 13:30 CST) is answered."
        result = send(self, sentence, repo)
        self.assertIsNone(result, "'%s' was refused: a claim that cites the owner's answer and its time must pass: %r"
                          % (core(sentence), str(result)[:160]))

    def test_a_move_between_lists_that_names_an_item_passes(self):
        repo = refusing()
        assert_refused(self, send(self, "item 874 is already answered.", repo), "874",
                       "item 874 is already answered.")  # scope: the bare claim is refused
        sentence = "Move item 874 from the answered list to the open list."
        assert_allowed(self, send(self, sentence, repo), sentence)

    def test_a_wait_until_an_answer_passes(self):
        repo = refusing()
        assert_refused(self, send(self, "item 874 is already answered.", repo), "874",
                       "item 874 is already answered.")  # scope: the bare claim is refused
        sentence = "Wait until item 874 is answered before you merge."
        assert_allowed(self, send(self, sentence, repo), sentence)

    def test_a_correction_that_an_answer_is_missing_passes(self):
        repo = refusing()
        assert_refused(self, send(self, "item 874 is already answered.", repo), "874",
                       "item 874 is already answered.")  # scope: the bare claim is refused
        sentence = "Correction: I wrote that item 874 was answered, and it is not."
        assert_allowed(self, send(self, sentence, repo), sentence)

    def test_a_message_that_claims_nothing_passes(self):
        assert_allowed(self, send(self, NO_CLAIM, refusing()), NO_CLAIM)

    def test_other_tools_are_not_judged(self):
        repo = refusing()
        assert_refused(self, send(self, CLAIM, repo), "874", CLAIM)  # scope: the store would refuse this text
        assert_allowed(self, judge(self, "Bash", {"command": "echo 'item 874 is already answered'"}, repo),
                       "echo 'item 874 is already answered'")
        assert_allowed(self, judge(self, CREATE_TOOL, {"prompt": "Review PR 3506 and report back."}, repo),
                       "Review PR 3506 and report back.")


class RefuseTests(unittest.TestCase):
    def test_a_claim_with_no_owner_answer_is_refused(self):
        assert_refused(self, send(self, CLAIM, refusing()), "874", CLAIM)

    def test_a_sentence_start_item_reference_is_refused(self):
        # A capitalised item reference at the start of a sentence is still a reference: the claim is the same.
        sentence = "Item 874 is already answered."
        assert_refused(self, send(self, sentence, refusing()), "874", sentence)

    def test_a_waiting_page_item_with_an_option_letter_is_refused(self):
        sentence = "waiting-page item 806 d approved by the owner."
        assert_refused(self, send(self, sentence, refusing()), "806", sentence)

    def test_a_page_reference_is_refused(self):
        sentence = "the owner ruled on page:131."
        assert_refused(self, send(self, sentence, refusing()), "131", sentence)

    def test_a_create_session_prompt_is_refused(self):
        sentence = "the owner ruled on page:131."
        assert_refused(self, judge(self, CREATE_TOOL, {"prompt": sentence}, refusing()), "131", sentence)

    def test_a_SendMessage_is_refused(self):
        sentence = "the owner ruled on page:131."
        result = judge(self, "SendMessage", {"to": "peer-lane", "message": sentence}, refusing())
        assert_refused(self, result, "131", sentence)

    def test_a_claim_in_only_the_second_sentence_is_refused(self):
        message = "item 806 is recommended, not answered. item 874 is already answered."
        assert_refused(self, send(self, message, refusing()), "874", "item 874 is already answered.")

    def test_a_claim_after_a_semicolon_is_refused(self):
        message = "item 806 is not answered; item 874 is already answered."
        assert_refused(self, send(self, message, refusing()), "874", "item 874 is already answered.")

    def test_each_item_reference_form_is_refused(self):
        for number, sentence in (
                ("874", "item 874 is already answered."),
                ("874", "item #874 is answered."),
                ("131", "the owner ruled on page:131."),
                ("874", "waiting-page item 874 is already answered.")):
            with self.subTest(form=sentence):
                assert_refused(self, send(self, sentence, refusing()), number, sentence)

    def test_each_claim_word_is_refused_in_any_case(self):
        for sentence in ("item 874 was approved by the coordinator.",
                         "item 874 was ruled on by the owner.",
                         "item 874 IS ANSWERED.",
                         "item 874 was Approved."):
            with self.subTest(sentence=sentence):
                assert_refused(self, send(self, sentence, refusing()), "874", sentence)

    def test_a_claim_beside_comment_openers_is_refused(self):
        sentence = "item 874 is already answered // see the page /* note */."
        assert_refused(self, send(self, sentence, refusing()), "874", sentence)

    def test_a_claim_after_a_closed_fence_is_refused(self):
        message = "```\nnothing to see here\n```\nitem 874 is already answered."
        assert_refused(self, send(self, message, refusing()), "874", "item 874 is already answered.")

    def test_a_lone_backtick_does_not_hide_the_claim(self):
        message = "Use a lone ` mark here. item 874 is already answered."
        assert_refused(self, send(self, message, refusing()), "874", "item 874 is already answered.")

    def test_a_possessive_does_not_hide_the_claim(self):
        sentence = "the owner's item 874 is already answered."
        assert_refused(self, send(self, sentence, refusing()), "874", sentence)

    def test_a_full_size_message_with_the_claim_on_the_last_line_is_refused(self):
        sentence = "item 874 is already answered."
        message = "detail " * 2500 + "\n" + sentence
        assert_refused(self, send(self, message, refusing()), "874", sentence)

    def test_a_plural_items_reference_is_refused(self):
        sentence = "Items 874 and 875 are answered."
        assert_refused(self, send(self, sentence, refusing()), "874", sentence)

    def test_an_item_number_with_a_letter_suffix_is_refused(self):
        sentence = "Item 874d is answered."
        assert_refused(self, send(self, sentence, refusing()), "874", sentence)

    def test_an_item_number_in_code_formatting_is_refused(self):
        sentence = "Item `874` is answered."
        assert_refused(self, send(self, sentence, refusing()), "874", sentence, echo=False)

    def test_an_item_split_by_a_line_break_is_refused(self):
        message = "Item 874 has been\nanswered by the owner."
        assert_refused(self, send(self, message, refusing()), "874", message, echo=False)


class StoreStateTests(unittest.TestCase):
    def test_an_item_with_a_last_answer_passes(self):
        assert_refused(self, send(self, CLAIM, refusing()), "874", CLAIM)  # scope: no answer, so refused
        answered = shared("last-answer", items=[item(874, answered=True)])
        assert_allowed(self, send(self, CLAIM, answered), CLAIM)

    def test_an_answers_file_passes(self):
        assert_refused(self, send(self, CLAIM, refusing()), "874", CLAIM)
        with_answer = shared("answers-file", items=[item(874)], answers=[answer(874)])
        assert_allowed(self, send(self, CLAIM, with_answer), CLAIM)

    def test_an_answer_held_only_by_origin_passes(self):
        repo = shared("origin-answer", items=[item(874)], origin_answers=[answer(874)])
        ref_path = EXPORT + "/answers/answer-874.json"
        # Scope: the local record branch lacks the answer, and origin's record branch holds it.
        self.assertFalse(ref_holds(repo, "refs/heads/" + RECORD_BRANCH, ref_path),
                         "the local record branch holds the origin-only answer: the case tests nothing")
        self.assertTrue(ref_holds(repo, "refs/remotes/origin/" + RECORD_BRANCH, ref_path),
                        "origin's record branch does not hold the origin-only answer")
        assert_allowed(self, send(self, CLAIM, repo), CLAIM)

    def test_an_item_absent_from_the_store_passes_and_says_so(self):
        assert_refused(self, send(self, CLAIM, refusing()), "874", CLAIM)  # scope: the same claim is refused
        absent = shared("no-874", items=[item(131), item(806)])
        result, stderr = judge_quiet(self, TOOL, {"session_id": SESSION, "message": CLAIM}, absent)
        assert_fail_open(self, result, stderr, CLAIM)

    def test_an_empty_store_passes(self):
        empty = shared("empty")
        assert_allowed(self, send(self, CLAIM, empty), CLAIM)

    def test_a_repo_with_no_registry_passes_and_says_so(self):
        absent = shared("no-registry", extras=False, items=[item(874)])
        result, stderr = judge_quiet(self, TOOL, {"session_id": SESSION, "message": CLAIM}, absent)
        assert_fail_open(self, result, stderr, CLAIM)

    def test_a_repo_with_no_record_branch_passes_and_says_so(self):
        absent = shared("no-branch", record=False)
        result, stderr = judge_quiet(self, TOOL, {"session_id": SESSION, "message": CLAIM}, absent)
        assert_fail_open(self, result, stderr, CLAIM)

    def test_a_full_size_store_refuses_its_last_item(self):
        repo = shared("full-size", items=[item(n) for n in range(1, 401)])
        self.assertTrue(ref_holds(repo, "refs/heads/" + RECORD_BRANCH, EXPORT + "/items/item-400.json"),
                        "the full-size store holds no item 400 file")
        sentence = "item 400 is already answered."
        assert_refused(self, send(self, sentence, repo), "400", sentence)


class CostTests(unittest.TestCase):
    def test_a_message_with_no_claim_starts_no_process(self):
        module = load_helper(self)
        repo = refusing()  # built before the block: its git starts are not the check's
        assert_refused(self, send(self, CLAIM, repo), "874", CLAIM)  # scope: the store would refuse a claim
        with cost_probe.children() as log:
            result = module.answered_claim_hit(TOOL, {"session_id": SESSION, "message": NO_CLAIM}, repo)
        assert_allowed(self, result, NO_CLAIM)
        self.assertEqual(log.argvs, [], "a message with no claim started %d child process(es): %r"
                         % (len(log.argvs), log.argvs))

    def test_a_claim_starts_at_most_two_git_reads(self):
        module = load_helper(self)
        repo = refusing()  # the fixture's own git starts are built before the block, so only the check's count
        with cost_probe.children() as log:
            result = module.answered_claim_hit(TOOL, {"session_id": SESSION, "message": CLAIM}, repo)
        assert_refused(self, result, "874", CLAIM)  # scope first: the claim was judged and refused
        self.assertGreaterEqual(len(log.argvs), 1, "a claim that was refused read no git: the store was not reached")
        self.assertLessEqual(len(log.argvs), 2, "a claim started %d child processes, not at most 2: %r"
                             % (len(log.argvs), log.argvs))
        self.assertEqual(set(cost_probe.names(log.argvs)), {"git"}, "a claim started a child that is not git: %r"
                         % (log.argvs,))

    def test_a_tool_that_is_not_judged_starts_no_process(self):
        module = load_helper(self)
        repo = refusing()  # built before the block: its git starts are not the check's
        with cost_probe.children() as log:
            result = module.answered_claim_hit("Bash", {"command": "echo 'item 874 is already answered'"}, repo)
        assert_allowed(self, result, "echo 'item 874 is already answered'")
        self.assertEqual(log.argvs, [], "a tool that is not judged started %d child process(es)" % len(log.argvs))


class GuardTests(unittest.TestCase):
    def test_guard_refuses_a_claim_with_no_owner_answer(self):
        decision = guard_decision(self, run_guard(refusing(), CLAIM))
        self.assertIsNotNone(decision, "guard.py allowed a send_message that says item 874 is answered, and the "
                                       "page holds no owner answer for it")
        self.assertEqual(decision.get("permissionDecision"), "deny",
                         "guard.py did not deny the claim: %r" % (decision,))
        reason = decision.get("permissionDecisionReason", "")
        self.assertTrue(reason.startswith(RULE + ": "),
                        "guard.py refused, but not on rule %s: %r" % (RULE, reason[:120]))
        self.assertIn("874", reason, "the guard's refusal does not name item 874: %r" % reason[:160])

    def test_guard_passes_a_message_with_no_claim(self):
        done = run_guard(refusing(), NO_CLAIM)
        decision = guard_decision(self, done)
        self.assertIsNone(decision, "guard.py refused a message with no claim: %r" % (decision,))
        self.assertEqual(done.stdout.strip(), "", "guard.py printed on an allow")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
