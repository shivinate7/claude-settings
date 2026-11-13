#!/usr/bin/env python3
"""Cases for skills/waiting-page/question_source.py: one source for a question's chat text and its page item.

render(spec) takes one list of options and returns {"chat": text, "item": dict}:
  - chat: the line `Page item: <id>`, then one line `a) <label>` per option, in order;
  - item: `options` and `shown` built from the same list. Keys are letters by position (a, b, c, ...), whatever keys the
    spec gives. Each option has an id: the spec's `id`, else the slug of its label, made unique. `shown` holds the
    {key, id, label} of each option (ruling R60, decision option-keys-are-letters).
  - spec `shown` is the shown list of an earlier item. When the new options do not extend it, position by position in key,
    id and label, render raises ValueError. When the spec carries `changes` ({key: note}), a changed option instead keeps
    its shown key, id and label and carries the note, so option-letters-frozen passes it.

The chat and the item it writes are read by question_form.chat_page_label_hit and frozen_letters_hit: no refusal.

Red on the current head: question_source.py is not there. render then stands in as a function that returns an empty chat
and item, so each case fails on its own assertion (no cite line, no raise, no option), never on an import error.

    python3 skills/waiting-page/test_question_source.py
"""
import importlib.util
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "hooks"))
import question_form  # noqa: E402  chat_page_label_hit and frozen_letters_hit: the one home of the two rules

ID = "merge-role-allow"
LABELS = ["Keep it as is", "Allow merge --role"]
NOTE = "Now means: hold the batch for the coordinator. Nothing else moved."
# The shown list an earlier item carries: the ids are the slugs of the labels, as render derives them.
EARLIER = [{"key": "a", "id": "keep-it-as-is", "label": "Keep it as is"},
           {"key": "b", "id": "allow-merge-role", "label": "Allow merge --role"}]
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _no_render(spec):
    """Stands in for render while question_source.py is not there. It returns no chat and no item, so each case fails
    on its own assertion, never on an import error."""
    return {"chat": "", "item": {}}


def load_render():
    """render from skills/waiting-page/question_source.py. A missing file is the stand-in; a file that fails to import
    is a real defect and raises."""
    if importlib.util.find_spec("question_source") is None:
        return _no_render
    import question_source
    return getattr(question_source, "render", _no_render)


RENDER = load_render()


def spec_of(labels, **over):
    """A render spec with one option per label, each with a gain and a lose line. The spec's keys are wrong on purpose
    (x0, x1, ...), so a case shows that render keys by position."""
    spec = {"id": ID, "options": [{"key": "x%d" % i, "label": label, "gain": "The runner merges alone.",
                                   "lose": "A second form on the shared list."} for i, label in enumerate(labels)]}
    spec.update(over)
    return spec


def chat_lines(result):
    return str(result.get("chat", "")).splitlines()


def option_lines(lines):
    return [line for line in lines if re.match(r"^[a-z]\) ", line)]


def options_of(case, item):
    options = item.get("options")
    case.assertIsInstance(options, list, "the item has no options list")
    return options


def raises_value_error(case, spec, why):
    try:
        RENDER(spec)
    except ValueError:
        return
    except Exception as exc:  # a crash is a wrong verdict, shown by name
        case.fail("%s: raised %s, not ValueError" % (why, type(exc).__name__))
    case.fail("%s: no ValueError was raised" % why)


class Chat(unittest.TestCase):
    def setUp(self):
        self.lines = chat_lines(RENDER(spec_of(LABELS)))

    def test_chat_cites_the_item(self):
        self.assertIn("Page item: " + ID, self.lines, "the chat has no `Page item: %s` line" % ID)

    def test_chat_writes_one_option_line_per_option_in_order(self):
        self.assertEqual(option_lines(self.lines), ["a) Keep it as is", "b) Allow merge --role"],
                         "the chat's option lines are not one `a) <label>` line per option, in order")


class Item(unittest.TestCase):
    def setUp(self):
        self.item = RENDER(spec_of(LABELS)).get("item", {})

    def test_options_keyed_by_position_whatever_the_spec_keys(self):
        keys = [o.get("key") for o in options_of(self, self.item)]
        self.assertEqual(keys, ["a", "b"], "the item's option keys are not the letters by position")

    def test_option_labels_are_the_spec_labels(self):
        labels = [o.get("label") for o in options_of(self, self.item)]
        self.assertEqual(labels, LABELS, "the item's option labels differ from the spec's")

    def test_shown_is_built_from_the_same_options(self):
        options = options_of(self, self.item)
        shown = [{"key": o.get("key"), "id": o.get("id"), "label": o.get("label")} for o in options]
        self.assertEqual(self.item.get("shown"), shown, "the item's shown is not the key, id and label of each option")

    def test_spec_id_is_used_when_given(self):
        spec = spec_of(LABELS)
        spec["options"][0]["id"] = "keep-it"
        spec["options"][1]["id"] = "allow-merge"
        ids = [o.get("id") for o in options_of(self, RENDER(spec).get("item", {}))]
        self.assertEqual(ids, ["keep-it", "allow-merge"], "a spec id is not the option's id")

    def test_id_is_the_label_slug_when_absent(self):
        ids = [o.get("id") for o in options_of(self, self.item)]
        self.assertEqual(ids, ["keep-it-as-is", "allow-merge-role"], "an option with no spec id has no label slug as its id")

    def test_ids_are_unique_when_labels_repeat(self):
        ids = [o.get("id") for o in options_of(self, RENDER(spec_of(["Hold", "Hold"])).get("item", {}))]
        self.assertEqual(len(set(ids)), 2, "two options with one label share an id: %r" % (ids,))
        self.assertTrue(all(isinstance(i, str) and SLUG.match(i) for i in ids),
                        "an id is not a non-empty lowercase slug: %r" % (ids,))


class Earlier(unittest.TestCase):
    def test_new_label_at_a_shown_position_raises(self):
        spec = spec_of(["Keep it as is", "Hold it for the coordinator"], shown=EARLIER)
        raises_value_error(self, spec, "a label at position b differs from the shown label")

    def test_new_id_at_a_shown_position_raises(self):
        spec = spec_of(LABELS, shown=EARLIER)
        spec["options"][0]["id"] = "keep-it"
        raises_value_error(self, spec, "an id at position a differs from the shown id")

    def test_appended_option_extends_shown_and_renders(self):
        spec = spec_of(LABELS + ["Hold it"], shown=EARLIER)
        item = RENDER(spec).get("item", {})
        options = options_of(self, item)
        self.assertEqual(len(options), 3, "an appended option is not rendered beside the shown two")
        self.assertEqual(item.get("shown", [])[:2], EARLIER, "the shown positions a and b changed")

    def test_changes_keep_the_shown_label_and_carry_the_note(self):
        spec = spec_of(["Keep it as is", "Hold it for the coordinator"], shown=EARLIER, changes={"b": NOTE})
        result = RENDER(spec)
        options = options_of(self, result.get("item", {}))
        self.assertEqual(options[1].get("label"), "Allow merge --role",
                         "a changed option does not keep its shown label, so option-letters-frozen would refuse it")
        self.assertEqual(options[1].get("note"), NOTE, "a changed option does not carry the change's note")
        self.assertIn("b) Allow merge --role", chat_lines(result), "the chat does not write the kept label for b")


class Feed(unittest.TestCase):
    def test_chat_and_item_pass_the_label_check(self):
        result = RENDER(spec_of(LABELS))
        lines = chat_lines(result)
        self.assertIn("Page item: " + ID, lines, "the chat has no cite, so there is nothing to compare")
        self.assertEqual(len(option_lines(lines)), 2, "the chat does not write one option line per option")
        item = result.get("item", {})
        refusal = question_form.chat_page_label_hit(ID, options_of(self, item), "\n".join(lines))
        self.assertEqual(refusal, "", "the chat question render wrote is refused by option-labels-match-chat: %r" % refusal)

    def test_changes_render_passes_the_freeze(self):
        result = RENDER(spec_of(["Keep it as is", "Hold it for the coordinator"], shown=EARLIER, changes={"b": NOTE}))
        lines = chat_lines(result)
        self.assertIn("Page item: " + ID, lines, "the chat has no cite, so the freeze and the label check read nothing")
        item = result.get("item", {})
        refusal = question_form.chat_page_label_hit(ID, options_of(self, item), "\n".join(lines))
        self.assertEqual(refusal, "", "the changes chat is refused by option-labels-match-chat: %r" % refusal)
        fn = getattr(question_form, "frozen_letters_hit", None)
        frozen = "" if fn is None else fn("update", dict(item))
        self.assertEqual(frozen, "", "the changes item is refused by option-letters-frozen: %r" % (frozen,))


class Sizes(unittest.TestCase):
    def test_full_size_26_options_key_a_to_z(self):
        labels = ["Choice %02d" % n for n in range(1, 27)]
        item = RENDER(spec_of(labels)).get("item", {})
        options = options_of(self, item)
        self.assertEqual([o.get("key") for o in options], list("abcdefghijklmnopqrstuvwxyz"),
                         "26 options are not keyed a to z by position")
        self.assertEqual(len(set(o.get("id") for o in options)), 26, "26 options do not carry 26 distinct ids")

    def test_empty_options_render_the_cite_only(self):
        result = RENDER(spec_of([]))
        self.assertEqual(chat_lines(result), ["Page item: " + ID], "an empty spec does not render the cite line alone")
        item = result.get("item", {})
        self.assertEqual(options_of(self, item), [], "an empty spec does not render an empty options list")
        self.assertEqual(item.get("shown"), [], "an empty spec does not render an empty shown list")


class Cli(unittest.TestCase):
    def run_cli(self, spec):
        import subprocess
        return subprocess.run([sys.executable, os.path.join(HERE, "question_source.py")], input=json.dumps(spec),
                              capture_output=True, text=True)

    def test_spec_with_no_shown_key_is_refused(self):
        """A re-render with no `shown` would skip the freeze, so the CLI wants `shown` ([] for a new item)."""
        r = self.run_cli({"id": ID, "options": [{"label": "Blue"}, {"label": "Red"}]})
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.startswith("refused: "), r.stderr)

    def test_spec_with_an_empty_shown_is_rendered(self):
        r = self.run_cli({"id": ID, "shown": [], "options": [{"label": "Blue"}]})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_options_that_is_not_a_list_is_refused_not_a_traceback(self):
        r = self.run_cli({"id": ID, "shown": [], "options": 5})
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.startswith("refused: "), r.stderr)

    def test_spec_with_no_id_is_refused(self):
        """A chat question names its item by id, so a spec with no id is refused, not rendered as `Page item: None`."""
        r = self.run_cli({"shown": [], "options": [{"label": "Blue"}, {"label": "Red"}]})
        self.assertEqual(r.returncode, 1, "a spec with no id was rendered: %r" % r.stdout[:120])
        self.assertTrue(r.stderr.startswith("refused: "), r.stderr)

    def refusal_of(self, r):
        """The refusal's text after `refused: `, or "" when the CLI did not refuse."""
        return r.stderr.strip()[len("refused: "):] if r.stderr.startswith("refused: ") else ""

    def assert_names_id(self, r):
        """The refusal names the id the shown entry lacks. A bare KeyError reads `'id'`, which names no cause."""
        msg = self.refusal_of(r)
        self.assertNotEqual(msg, "'id'", "the refusal is a bare KeyError, not a message: %r" % r.stderr)
        self.assertRegex(msg, r"\bid\b", "the refusal does not name the id the shown entry lacks: %r" % msg)

    def test_shown_entry_with_no_id_is_refused_with_a_message_naming_the_id(self):
        """A shown entry with no id can match no option. With `changes` naming that option, render reads its id."""
        no_id = [{k: v for k, v in entry.items() if k != "id"} for entry in EARLIER]
        r = self.run_cli({"id": ID, "shown": no_id, "changes": {"a": NOTE},
                          "options": [{"label": "Keep it as is", "gain": "g", "lose": "l"},
                                      {"label": "Allow merge --role", "gain": "g", "lose": "l"}]})
        self.assertEqual(r.returncode, 1, "a shown entry with no id was rendered: %r" % r.stdout[:120])
        self.assert_names_id(r)

    def test_shown_entry_with_no_id_is_refused_without_changes_naming_the_id(self):
        """The same shown entry with no `changes`: the option differs from its shown entry, and the refusal names the id."""
        no_id = [{k: v for k, v in entry.items() if k != "id"} for entry in EARLIER]
        r = self.run_cli({"id": ID, "shown": no_id,
                          "options": [{"label": "Keep it as is", "gain": "g", "lose": "l"},
                                      {"label": "Allow merge --role", "gain": "g", "lose": "l"}]})
        self.assertEqual(r.returncode, 1, "a shown entry with no id was rendered: %r" % r.stdout[:120])
        self.assert_names_id(r)

    def test_existing_item_with_an_empty_shown_is_refused(self):
        """A spec that names an existing item carries that item's shown list: `shown: []` would skip the freeze."""
        r = self.run_cli({"id": ID, "existing": True, "shown": [], "options": [{"label": "Blue"}]})
        self.assertEqual(r.returncode, 1, "an existing item was rendered with an empty shown list")
        self.assertTrue(r.stderr.startswith("refused: "), r.stderr)

    def test_existing_item_with_its_shown_list_is_rendered(self):
        """Control, green on the current head: an existing item that carries its shown list renders."""
        r = self.run_cli({"id": ID, "existing": True, "shown": EARLIER,
                          "options": [{"label": "Keep it as is", "gain": "g", "lose": "l"},
                                      {"label": "Allow merge --role", "gain": "g", "lose": "l"}]})
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
