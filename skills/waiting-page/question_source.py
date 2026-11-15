#!/usr/bin/env python3
"""One source for a question's chat text and its waiting-page item (ruling R60, decision option-keys-are-letters).

A session that asks the owner in the chat and on the page writes two copies of one option list. Written by hand, the
copies drift: a letter then names one option in the chat and another on the page. `render` builds both from one spec,
so they cannot differ.

    python3 skills/waiting-page/question_source.py < spec.json      prints {"chat": ..., "item": ...} as JSON

The spec is the item's own fields, with `options`, and optionally:
  id       required: the chat question cites the item by it.
  shown    required by the command line, a list; [] for a new item. The `shown` list of an earlier item: [{key, id, label}, ...]. The new options must extend it, position by
           position, in key, id and label, or render raises ValueError. That is the freeze (guard rule
           `option-letters-frozen`) read before the write, not after it.
  existing true when the spec names an item already on the page: `shown` must then be that item's, never empty.
  changes  {key: note}. A shown option listed here keeps its shown key, id and label and carries the note as its `note`
           (the page shows it on the card). Use it when a rule changes what an option means: the letter does not move.

It returns {"chat": text, "item": dict}.
  chat  the line `Page item: <id>`, then one line `a) <label>` per option, in order.
  item  the spec's other fields, `options` and `shown`. Each option is keyed by its position (a, b, c, ...), whatever
        key the spec gives, and carries an id: the spec's `id`, else the slug of its label, made unique. `shown` holds
        the {key, id, label} of each option, so a first write carries a shown equal to its options.

At most 26 options: the page repeats its letters after Z. Standard library only. Cost: one process, no file, no network.
"""
import json
import re
import string
import sys

CITE = "Page item: "
SHOWN_FIELDS = ("key", "id", "label")
NOT_ITEM_FIELDS = ("options", "shown", "changes", "existing")  # the spec's own controls: the item holds options and shown it built


def slug(label):
    """The label as a lowercase slug of letters, digits and hyphens. A lone letter would read as an option key, so it
    gets a prefix; a label with no letter or digit becomes `option`."""
    text = re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-")
    if not text:
        return "option"
    return "option-" + text if len(text) == 1 and text.isalpha() else text


def unique(candidate, used):
    """`candidate`, or `candidate-2`, `candidate-3`, ... when `used` already holds it."""
    found, n = candidate, 1
    while found in used:
        n += 1
        found = "%s-%d" % (candidate, n)
    return found


def triple(entry):
    return tuple(entry.get(field) for field in SHOWN_FIELDS)


def render(spec):
    """{"chat": text, "item": dict} for one spec. ValueError when the spec has no id, a shown entry has no id, or the options do not extend the spec's shown list."""
    options = spec.get("options") or []
    shown = spec.get("shown") or []
    changes = spec.get("changes") or {}
    if not isinstance(spec.get("id"), str) or not spec["id"].strip():
        raise ValueError("the spec carries no `id`: the chat question cites the item by it")
    if spec.get("existing") and not shown:
        raise ValueError("the spec names an existing item but carries an empty `shown`: give the item's shown list")
    for at, entry in enumerate(shown):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
            raise ValueError("shown entry %d has no `id`" % (at + 1))
    if len(options) > len(string.ascii_lowercase):
        raise ValueError("more than 26 options: the page repeats its letters after Z")
    if len(options) < len(shown):
        raise ValueError("fewer options than shown: an option never drops out")
    held = {entry.get("key") for entry in shown}
    unplaced = [key for key in changes if key not in held]
    if unplaced:
        raise ValueError("changes names %s, which is no shown option" % ", ".join(map(str, unplaced)))
    built, used = [], set()
    for at, given in enumerate(options):
        key = string.ascii_lowercase[at]
        if at < len(shown) and key in changes:
            # The option keeps what was shown; only its note says what changed.
            kept = shown[at]
            one = dict(given, key=kept["key"], id=kept["id"], label=kept["label"], note=changes[key])
        else:
            one = dict(given, key=key)
            one["id"] = unique(str(given["id"]) if given.get("id") else slug(given.get("label", "")), used)
            if at < len(shown) and triple(one) != triple(shown[at]):
                raise ValueError("option %s differs from the option shown at its letter" % key)
        used.add(one["id"])
        built.append(one)
    item = {k: v for k, v in spec.items() if k not in NOT_ITEM_FIELDS}
    item["options"] = built
    item["shown"] = [{field: one[field] for field in SHOWN_FIELDS} for one in built]
    lines = [CITE + str(spec.get("id"))] + ["%s) %s" % (one["key"], one["label"]) for one in built]
    return {"chat": "\n".join(lines), "item": item}


def main():
    try:
        spec = json.load(sys.stdin)
        if isinstance(spec, dict) and not isinstance(spec.get("shown"), list):
            raise ValueError("the spec carries no `shown`: give the item's shown list, or [] for a new item")
        result = render(spec)
    except (ValueError, AttributeError, KeyError, TypeError) as err:
        print("refused: %s" % err, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
