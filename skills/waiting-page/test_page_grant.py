#!/usr/bin/env python3
"""Cases for skills/waiting-page/page_grant.py, the checker that says whether a fetched page answer is the owner's grant.

    python3 -m unittest skills/waiting-page/test_page_grant.py

PAGE_GRANT_UNDER_TEST names the script to run (default: page_grant.py beside this file), so the same cases run
against another checkout and show red there.

The checker reads only what a session fetched with ArtifactData (DIR/answers/<ID>.json, DIR/items/<ID>.json) and the
repo's extras file (its "artifacts" registry, read by lint/layout.py). Relay text is never an input. Each case builds
its own fixture under this run's folder, so no fixture file is checked in.

Verdict, one line on stdout. A counted line is page_grant.COUNTED_LINE with its fields filled in, plus
note=<json string> when the answer has a note (exit 0).
  not counted: <reason>                                                  exit 1
  unknown: <reason>                                                      exit 2 (no readable registry, a fetched file not one JSON object)
The rules are SKILL.md "Read the answers" ("A decision answer is clear only when") and "Route and close".
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CMD = os.environ.get("PAGE_GRANT_UNDER_TEST") or os.path.join(HERE, "page_grant.py")
LINT = os.path.realpath(os.path.join(HERE, "..", "..", "lint"))
sys.path.insert(0, LINT)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

RUN_FOLDER = None
EXTRAS = ".claude/layout-extras.json"  # the repo's extras file, where lint/layout.json "extras" points
PAGE_ID = "Wp7kQ2mZx9LrT4vB"
PAGE_URL = "https://claude.ai/artifact/" + PAGE_ID
PAGE_CODE_URL = "https://claude.ai/code/artifact/" + PAGE_ID
NOTES_ID = "Nq3hT8sVc2YbK5wD"
NOTES_URL = "https://claude.ai/artifact/" + NOTES_ID
OTHER_URL = "https://claude.ai/artifact/Zz9Qq1Ww2Ee3Rr4T"  # an artifact link that the registry does not hold
ITEM_ID = "review-fix-check-go"
ITEM_N = 231
ADDED = "2026-11-04T12:00:00Z"  # the item's `added`, before the answer
AT = "2026-11-04T13:56:29.078Z"  # the answer's `at`, as the live answer of item 231 holds it
ABSENT = object()  # set a field to ABSENT to leave it out of a fixture
PICK = "a"  # the pick every case passes unless it names another; a decision with no pick is not counted


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def merged(doc, fields):
    doc.update(fields)
    return {key: value for key, value in doc.items() if value is not ABSENT}


def options(keys):
    return [{"key": key, "label": "Option " + key.upper()} for key in keys]


def item(**fields):
    """Item 231 as the page holds it: an open pick-one decision with options a and b."""
    doc = {"id": ITEM_ID, "n": ITEM_N, "added": ADDED, "status": "open", "multi": False, "ranked": False,
           "arbiter": False, "options": options("ab")}
    return merged(doc, fields)


def answer(**fields):
    """The owner's answer to item 231 as the page saves it: choice a, no note."""
    return merged({"at": AT, "choice": "a", "item": ITEM_ID, "n": ITEM_N, "note": ""}, fields)


def label_of(choice):
    """The label the counted line prints for a choice: the option's label, a list of them for several, null for overturn.
    options() names each label, so the key fixes it."""
    if choice == "overturn":
        return None
    if "+" in choice:
        return ["Option " + key.upper() for key in choice.split("+")]
    return "Option " + choice.upper()


def verdict(choice, note=None):
    """The counted line for item 231. `choice` is a key, or `a+c` for a list. The label goes after `at`, before `note`."""
    line = "counted item=%s n=%d choice=%s at=%s label=%s" % (ITEM_ID, ITEM_N, choice, AT, json.dumps(label_of(choice)))
    return line if note is None else line + " note=" + json.dumps(note)


def registry():
    """The repo's registry: a notes page that is not exported, and the waiting page last."""
    return [
        {"id": "notes", "url": NOTES_URL, "role": "notes", "account": "main", "export": False},
        {"id": "waiting", "url": PAGE_URL, "role": "waiting-page", "account": "main"},
    ]


def full_registry():
    """Full size: 24 entries before the waiting page, which stays last."""
    many = [{"id": "entry-%02d" % n, "url": "https://claude.ai/artifact/Entry%02dAbCdEfGh0" % n,
             "role": "notes-%02d" % n, "account": "main", "export": False} for n in range(1, 25)]
    return many + registry()[1:]


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def snapshot(folder):
    """{relative path: bytes} for every file under `folder`."""
    out = {}
    for dirpath, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                out[os.path.relpath(path, folder)] = handle.read()
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)  # test-temp-standard: never the system temp dir
        self.addCleanup(self.tmp.cleanup)

    def repo(self, artifacts=None, extras=True):
        """A repo root with its extras file. `artifacts` replaces the default registry; extras=False leaves the file out."""
        root = tempfile.mkdtemp(prefix="repo-", dir=self.tmp.name)
        if extras:
            registry_list = registry() if artifacts is None else artifacts
            # lint/layout.py refuses an extras file with no "kinds" object, so the fixture carries an empty one.
            write_text(os.path.join(root, EXTRAS), json.dumps({"kinds": {}, "artifacts": registry_list}))
        return root

    def new_fetch(self):
        """A fetch folder made by the checker's own `--new-fetch`, as SKILL.md has a session make one per check."""
        r = subprocess.run([sys.executable, CMD, "--new-fetch", self.tmp.name], capture_output=True, text=True,
                           timeout=60, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(r.returncode, 0, "--new-fetch failed: stdout %r, stderr %r" % (r.stdout, r.stderr))
        line = r.stdout.strip()
        self.assertTrue(line.startswith("fetch "), "--new-fetch printed %r, not `fetch <dir>`" % line)
        return line[len("fetch "):]

    def fetch(self, items=None, answers=None, hand=False):
        """A fetched folder. A collection given as None has no folder, as ArtifactData leaves it for a missing document.
        A document given as a str is written verbatim, so a case can hold a file that is not JSON. hand=True builds the
        folder by hand, with no `--new-fetch`, as a session that skips the step would."""
        root = tempfile.mkdtemp(prefix="fetched-", dir=self.tmp.name) if hand else self.new_fetch()
        for name, docs in (("items", items), ("answers", answers)):
            if docs is None:
                continue
            os.makedirs(os.path.join(root, name), exist_ok=True)
            for doc_id, data in docs.items():
                write_text(os.path.join(root, name, doc_id + ".json"), data if isinstance(data, str) else json.dumps(data))
        return root

    def pair(self, item_fields=None, answer_fields=None):
        """A fetched folder with item 231 and its answer, each with the given fields set or left out (ABSENT)."""
        return self.fetch(items={ITEM_ID: item(**(item_fields or {}))},
                          answers={ITEM_ID: answer(**(answer_fields or {}))})

    def check(self, root, fetched, page=PAGE_URL, item_id=ITEM_ID, pick=PICK):
        args = [sys.executable, CMD, "--root", root, "--page-url", page, "--item", item_id, "--fetched", fetched]
        if pick is not None:
            args += ["--pick", pick]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(args, capture_output=True, text=True, timeout=60, env=env)

    def assertCounted(self, r, line):
        self.assertEqual(r.returncode, 0, "a clear answer is not counted: exit %d, stdout %r, stderr %r"
                         % (r.returncode, r.stdout, r.stderr))
        self.assertEqual(r.stdout.splitlines(), [line], "the counted line differs from the answer")

    def assertLabelled(self, r, line):
        """The counted line with its label. A line with no label, or a label not quoted as JSON, fails on that alone."""
        self.assertEqual(r.returncode, 0, "a clear answer is not counted: exit %d, stdout %r, stderr %r"
                         % (r.returncode, r.stdout, r.stderr))
        self.assertEqual(r.stdout.splitlines(), [line],
                         "the counted line does not print the picked option's label as label=<json>")

    def assertNotCounted(self, r, case, reason=None):
        """`reason`, a lower-case word, must appear in the verdict's reason, so the case fails for its own rule."""
        self.assertEqual(r.returncode, 1, "%s: expected exit 1, got %d, stdout %r, stderr %r"
                         % (case, r.returncode, r.stdout, r.stderr))
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 1, "%s: expected one verdict line, got %r" % (case, lines))
        self.assertTrue(lines[0].startswith("not counted: "), "%s: verdict is not `not counted:`: %r" % (case, lines[0]))
        if reason is not None:
            self.assertIn(reason, lines[0].lower(), "%s: the reason does not name %r: %r" % (case, reason, lines[0]))

    def assertUnknown(self, r, case):
        self.assertEqual(r.returncode, 2, "%s: expected exit 2, got %d, stdout %r, stderr %r"
                         % (case, r.returncode, r.stdout, r.stderr))
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 1, "%s: expected one verdict line, got %r" % (case, lines))
        self.assertTrue(lines[0].startswith("unknown: "), "%s: verdict is not `unknown:`: %r" % (case, lines[0]))
        self.assertNotIn("Traceback", r.stderr, "%s: the checker crashed" % case)


class Counted(Base):
    def test_replay_item_231_counted(self):
        r = self.check(self.repo(), self.pair(), pick="a")
        self.assertCounted(r, 'counted item=review-fix-check-go n=231 choice=a at=2026-11-04T13:56:29.078Z label="Option A"')

    def test_code_artifact_form_of_the_page_counted(self):
        r = self.check(self.repo(), self.pair(), page=PAGE_CODE_URL, pick="a")
        self.assertCounted(r, verdict("a"))

    def test_note_printed_as_json_string(self):
        r = self.check(self.repo(), self.pair(answer_fields={"note": 'Ship "it" now'}), pick="a")
        self.assertCounted(r, verdict("a", note='Ship "it" now'))

    def test_at_later_by_milliseconds_in_same_second_counted(self):
        r = self.check(self.repo(), self.pair(item_fields={"added": "2026-11-04T13:56:29Z"}), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_multi_list_counted_as_joined_keys(self):
        r = self.check(self.repo(), self.pair(item_fields={"multi": True, "options": options("abc")},
                                              answer_fields={"choice": ["a", "c"]}), pick="a+c")
        self.assertCounted(r, verdict("a+c"))

    def test_overturn_on_arbiter_ruling_counted(self):
        r = self.check(self.repo(), self.pair(item_fields={"arbiter": True}, answer_fields={"choice": "overturn"}),
                       pick="overturn")
        self.assertCounted(r, verdict("overturn"))

    def test_open_item_with_lane_set_counted(self):
        """The relay case: a lane took the answer, so the item is still open with its `lane` set. The checker counts it."""
        r = self.check(self.repo(), self.pair(item_fields={"lane": "owner-word-relay"}), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_open_item_with_lane_and_last_answer_and_answer_kept_counted(self):
        """The answer is kept until the receiver reports done: the item is open with `lane` and `lastAnswer` set, and
        answers/<id> is still there. Counted on the relayed pick: the checker never reads `lane` or `lastAnswer`."""
        last = {"choice": "a", "note": "", "at": AT}
        r = self.check(self.repo(), self.pair(item_fields={"lane": "owner-word-relay", "lastAnswer": last}), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_item_with_no_status_field_counted(self):
        """An item with no `status` field at all is open, as the page reads it. A checker that read a missing status
        as closed would refuse this answer."""
        r = self.check(self.repo(), self.pair(item_fields={"status": ABSENT}), pick="a")
        self.assertCounted(r, verdict("a"))

    # The doc key is the item id (roadmap step page-item-id-check).
    def test_item_with_no_id_field_counted_under_its_key(self):
        """The key of items/<key> is the item's id, so an item with no `id` field is counted under its key. Red on the old
        checker, which refuses it: `answer is for item ..., not ...`, because it reads item.id."""
        r = self.check(self.repo(), self.pair(item_fields={"id": ABSENT}), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_item_whose_id_field_differs_from_its_key_counted(self):
        """An `id` field that differs from the key is ignored: the key is the id. Red on the old checker, which refuses it
        with `answer is for item ..., not ...`, because it reads item.id."""
        r = self.check(self.repo(), self.pair(item_fields={"id": "other-id"}), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_closed_arbiter_ruling_overturn_counted(self):
        """An arbiter ruling is written closed; its overturn still counts."""
        r = self.check(self.repo(), self.pair(item_fields={"status": "closed", "arbiter": True},
                                              answer_fields={"choice": "overturn"}), pick="overturn")
        self.assertCounted(r, verdict("overturn"))

    def test_added_with_explicit_offset_counted(self):
        """06:00 at -06:00 is 12:00Z, so the answer at 13:56Z is still later."""
        r = self.check(self.repo(), self.pair(item_fields={"added": "2026-11-04T06:00:00-06:00"}), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_pick_matching_counted(self):
        r = self.check(self.repo(), self.pair(), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_pick_multi_matching_counted(self):
        r = self.check(self.repo(), self.pair(item_fields={"multi": True, "options": options("abc")},
                                              answer_fields={"choice": ["a", "c"]}), pick="a+c")
        self.assertCounted(r, verdict("a+c"))

    def test_full_size_options_answer_last_key_counted(self):
        r = self.check(self.repo(), self.pair(item_fields={"options": options("abcdefghijkl")},
                                              answer_fields={"choice": "l"}), pick="l")
        self.assertCounted(r, verdict("l"))

    def test_full_size_registry_waiting_page_last_counted(self):
        r = self.check(self.repo(artifacts=full_registry()), self.pair(), pick="a")
        self.assertCounted(r, verdict("a"))

    def test_checker_writes_only_its_stamp(self):
        root, fetched = self.repo(), self.pair()
        before = (snapshot(root), snapshot(fetched))
        r = self.check(root, fetched, pick="a")
        self.assertCounted(r, verdict("a"))
        self.assertEqual((snapshot(root), snapshot(fetched)), before, "the checker changed a file under root or fetched")
        self.assertFalse(os.path.exists(fetched + ".stamp"), "the checker left its stamp unused")
        self.assertTrue(os.path.isfile(fetched + ".stamp.used"), "the checker did not keep its used stamp")


class CountedLabel(Base):
    """The counted line prints the picked option's label as `label=<JSON>`, after `at` and before `note`, on one line."""

    def test_counted_line_prints_the_picked_option_label(self):
        r = self.check(self.repo(), self.pair(), pick="a")
        self.assertLabelled(r, 'counted item=review-fix-check-go n=231 choice=a at=%s label="Option A"' % AT)

    def test_label_with_quotes_a_fake_token_and_a_newline_prints_one_json_string(self):
        label = 'Set "relayed" choice=b at=X\nin settings.json'
        opts = [{"key": "a", "label": label}, {"key": "b", "label": "Option B"}]
        r = self.check(self.repo(), self.pair(item_fields={"options": opts}), pick="a")
        self.assertLabelled(r, 'counted item=review-fix-check-go n=231 choice=a at=%s '
                               'label="Set \\"relayed\\" choice=b at=X\\nin settings.json"' % AT)

    def test_multi_item_prints_its_labels_as_a_json_list(self):
        r = self.check(self.repo(), self.pair(item_fields={"multi": True, "options": options("abc")},
                                              answer_fields={"choice": ["a", "c"]}), pick="a+c")
        self.assertLabelled(r, 'counted item=review-fix-check-go n=231 choice=a+c at=%s label=["Option A", "Option C"]' % AT)

    def test_overturn_prints_label_null(self):
        r = self.check(self.repo(), self.pair(item_fields={"arbiter": True}, answer_fields={"choice": "overturn"}),
                       pick="overturn")
        self.assertLabelled(r, "counted item=review-fix-check-go n=231 choice=overturn at=%s label=null" % AT)


class NotCounted(Base):
    def test_relay_only_no_answers_folder(self):
        fetched = self.fetch(items={ITEM_ID: item()}, answers=None)
        self.assertNotCounted(self.check(self.repo(), fetched), "no saved answer")

    def test_answers_folder_holds_no_document(self):
        fetched = self.fetch(items={ITEM_ID: item()}, answers={})
        self.assertNotCounted(self.check(self.repo(), fetched), "answers folder is empty")

    def test_item_file_missing(self):
        fetched = self.fetch(items=None, answers={ITEM_ID: answer()})
        self.assertNotCounted(self.check(self.repo(), fetched), "item file missing")

    def test_answer_names_another_item(self):
        r = self.check(self.repo(), self.pair(answer_fields={"item": "other-item", "n": 999}))
        self.assertNotCounted(r, "answer names another item (item and n differ)")

    def test_n_matches_but_item_differs(self):
        r = self.check(self.repo(), self.pair(answer_fields={"item": "other-item"}))
        self.assertNotCounted(r, "answer n matches, item differs")

    def test_n_differs_but_item_matches(self):
        r = self.check(self.repo(), self.pair(answer_fields={"n": 999}))
        self.assertNotCounted(r, "answer n differs, item matches")

    def test_at_earlier_than_added(self):
        r = self.check(self.repo(), self.pair(answer_fields={"at": "2026-11-04T11:00:00Z"}))
        self.assertNotCounted(r, "answer at is earlier than item added")

    def test_at_equal_to_added(self):
        r = self.check(self.repo(), self.pair(item_fields={"added": AT}))
        self.assertNotCounted(r, "answer at equals item added (later is required)")

    def test_page_url_not_in_registry(self):
        r = self.check(self.repo(), self.pair(), page=OTHER_URL)
        self.assertNotCounted(r, "page URL is not the registered waiting page")

    def test_page_url_is_another_registry_entry(self):
        r = self.check(self.repo(), self.pair(), page=NOTES_URL)
        self.assertNotCounted(r, "page URL is a registry entry that is not the waiting page")

    def test_choice_not_an_option_key(self):
        r = self.check(self.repo(), self.pair(answer_fields={"choice": "z"}))
        self.assertNotCounted(r, "choice is not an option key")

    def test_choice_none(self):
        r = self.check(self.repo(), self.pair(answer_fields={"choice": "none"}))
        self.assertNotCounted(r, "choice none asks for new options")

    def test_choice_none_with_clear_direction(self):
        r = self.check(self.repo(), self.pair(answer_fields={"choice": "none", "note": "Take option b, go ahead"}))
        self.assertNotCounted(r, "choice none with a note is still not counted: the routing session judges the note")

    def test_overturn_on_non_arbiter_item(self):
        r = self.check(self.repo(), self.pair(answer_fields={"choice": "overturn"}))
        self.assertNotCounted(r, "overturn on an item with arbiter not true")

    def test_multi_empty_list(self):
        r = self.check(self.repo(), self.pair(item_fields={"multi": True, "options": options("abc")},
                                              answer_fields={"choice": []}))
        self.assertNotCounted(r, "multi choice is an empty list")

    def test_multi_repeated_key(self):
        r = self.check(self.repo(), self.pair(item_fields={"multi": True, "options": options("abc")},
                                              answer_fields={"choice": ["a", "a"]}))
        self.assertNotCounted(r, "multi choice repeats a key")

    def test_multi_entry_not_an_option_key(self):
        r = self.check(self.repo(), self.pair(item_fields={"multi": True, "options": options("abc")},
                                              answer_fields={"choice": ["a", "z"]}))
        self.assertNotCounted(r, "multi choice holds a key that is not an option")

    def test_multi_string_choice(self):
        r = self.check(self.repo(), self.pair(item_fields={"multi": True, "options": options("abc")},
                                              answer_fields={"choice": "a"}))
        self.assertNotCounted(r, "a string choice on a multi item")

    def test_list_choice_on_pick_one_item(self):
        r = self.check(self.repo(), self.pair(answer_fields={"choice": ["a"]}))
        self.assertNotCounted(r, "a list choice on a pick-one item")

    def test_task_note_only_no_done(self):
        r = self.check(self.repo(), self.pair(item_fields={"kind": "task", "options": []},
                                              answer_fields={"choice": ABSENT, "note": "Half done, see context"}))
        self.assertNotCounted(r, "task answer with a note and no done")

    def test_pick_mismatch(self):
        r = self.check(self.repo(), self.pair(), pick="b")
        self.assertNotCounted(r, "page pick is a, the relayed pick is b")

    def test_status_closed_decision_not_counted(self):
        r = self.check(self.repo(), self.pair(item_fields={"status": "closed"}))
        self.assertNotCounted(r, "item status closed: only an open item takes an answer", reason="status")

    def test_closed_arbiter_ruling_answer_not_overturn_not_counted(self):
        r = self.check(self.repo(), self.pair(item_fields={"status": "closed", "arbiter": True}))
        self.assertNotCounted(r, "closed arbiter ruling answered with a pick: only overturn passes", reason="status")

    def test_answer_at_zone_less_not_counted(self):
        r = self.check(self.repo(), self.pair(answer_fields={"at": "2026-11-04T13:56:29.078"}))
        self.assertNotCounted(r, "answer at has no zone", reason="zone")

    def test_item_added_zone_less_not_counted(self):
        r = self.check(self.repo(), self.pair(item_fields={"added": "2026-11-04T10:00:00"}))
        self.assertNotCounted(r, "item added has no zone", reason="zone")

    def test_decision_without_pick_not_counted(self):
        r = self.check(self.repo(), self.pair(), pick=None)
        self.assertNotCounted(r, "decision run with no --pick", reason="pick")

    def test_task_with_done_not_counted(self):
        """A task answer grants no act, even with done set true."""
        r = self.check(self.repo(), self.pair(item_fields={"kind": "task", "options": []},
                                              answer_fields={"choice": ABSENT, "done": True}), pick="done")
        self.assertNotCounted(r, "task answer with done true", reason="task")


class Provenance(Base):
    """Decision relayed-grant-read-from-page: the files must come from this one fetch, never an older one or a hand."""

    def test_new_fetch_makes_an_empty_folder_and_a_stamp_beside_it(self):
        fetched = self.new_fetch()
        self.assertEqual(os.listdir(fetched), [], "the new fetch folder is not empty")
        self.assertTrue(os.path.isfile(fetched + ".stamp"), "no stamp beside the new fetch folder")

    def test_hand_built_folder_not_counted(self):
        fetched = self.fetch(items={ITEM_ID: item()}, answers={ITEM_ID: answer()}, hand=True)
        self.assertNotCounted(self.check(self.repo(), fetched), "folder made by hand", reason="--new-fetch")

    def test_reused_folder_not_counted(self):
        root, fetched = self.repo(), self.pair()
        self.assertCounted(self.check(root, fetched), verdict("a"))
        self.assertNotCounted(self.check(root, fetched), "same folder checked twice", reason="already checked")

    def test_withdrawn_answer_left_in_reused_folder_not_counted(self):
        """The owner withdraws the answer; a re-fetch into the old folder saves no file, so the old answer stays."""
        root, fetched = self.repo(), self.pair()
        self.assertNotCounted(self.check(root, fetched, pick="b"), "first check, wrong pick")
        self.assertNotCounted(self.check(root, fetched), "withdrawn answer left in a reused folder",
                              reason="already checked")

    def test_answer_older_than_the_stamp_not_counted(self):
        fetched = self.pair()
        made = os.stat(fetched + ".stamp").st_mtime_ns
        os.utime(os.path.join(fetched, "answers", ITEM_ID + ".json"), ns=(made - 10 ** 9, made - 10 ** 9))
        self.assertNotCounted(self.check(self.repo(), fetched), "answer file older than the fetch", reason="older")

    def test_folder_with_another_items_file_not_counted(self):
        fetched = self.fetch(items={ITEM_ID: item(), "other-item": item(id="other-item")},
                             answers={ITEM_ID: answer()})
        self.assertNotCounted(self.check(self.repo(), fetched), "folder holds another item's file", reason="holds")

    def test_wrong_page_url_check_uses_the_folder_up(self):
        root, fetched = self.repo(), self.pair()
        self.assertNotCounted(self.check(root, fetched, page=OTHER_URL), "first check, wrong page URL")
        self.assertNotCounted(self.check(root, fetched), "same folder, right URL", reason="already checked")

    def test_unknown_registry_check_uses_the_folder_up(self):
        fetched = self.pair()
        self.assertUnknown(self.check(self.repo(extras=False), fetched), "first check, repo with no extras file")
        self.assertNotCounted(self.check(self.repo(), fetched), "same folder, right root", reason="already checked")

    def test_stray_file_check_uses_the_folder_up(self):
        fetched = self.fetch(items={ITEM_ID: item(), "other-item": item(id="other-item")},
                             answers={ITEM_ID: answer()})
        self.assertNotCounted(self.check(self.repo(), fetched), "first check, stray file", reason="holds")
        os.remove(os.path.join(fetched, "items", "other-item.json"))
        self.assertNotCounted(self.check(self.repo(), fetched), "stray file removed", reason="already checked")

    def test_stamp_copied_onto_a_hand_built_folder_not_counted(self):
        made = self.new_fetch()
        fetched = self.fetch(items={ITEM_ID: item()}, answers={ITEM_ID: answer()}, hand=True)
        shutil.copy(made + ".stamp", fetched + ".stamp")
        self.assertNotCounted(self.check(self.repo(), fetched), "another folder's stamp", reason="--new-fetch")


class Unknown(Base):
    def test_no_extras_file(self):
        r = self.check(self.repo(extras=False), self.pair())
        self.assertUnknown(r, "repo has no extras file")

    def test_registry_holds_no_artifacts(self):
        r = self.check(self.repo(artifacts=[]), self.pair())
        self.assertUnknown(r, "registry is empty, so no waiting page is known")

    def test_fetched_answer_not_json(self):
        fetched = self.fetch(items={ITEM_ID: item()}, answers={ITEM_ID: "not json {"})
        self.assertUnknown(self.check(self.repo(), fetched), "fetched answer file is not JSON")


if __name__ == "__main__":
    unittest.main()
