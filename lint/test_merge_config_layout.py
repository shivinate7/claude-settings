#!/usr/bin/env python3
"""Cases for the layout of .github/stamp.json: a JSON array that holds more than three strings keeps each string on its own line.
Standard library only.

    python3 lint/test_merge_config_layout.py

Lanes add one name to merge.readyChecks, merge.lintSuites or merge.keepBranches. When every name sits on one line, two lanes that
each add a name edit that line, and the merge of main into the second lane conflicts. One name per line lets git merge two adds
that touch different lines (decisions one-layout-every-repo and notes-merge-union).

The rule: an array with more than LIMIT string entries has no two entries that start on one line. An array of LIMIT strings or
fewer is not judged. Reading the layout needs the line of each entry, which json.load does not give, so array_entries scans the
text. It reads each string with json's own string reader, so a bracket, comma, quote or comment opener inside a string never
reaches the scan, and it takes no more than valid JSON. The real-file cases first check that the scan read every array the way
json.load reads it, so a layout verdict on the file is a verdict on the arrays the merge tool reads.

The file cases read this checkout's .github/stamp.json. The text cases (the table CASES) run the scan on synthetic text and pass
before the file is laid out: they show each defect is seen and each layout the rule allows is not. The shape control shows the
file still holds the lists the merge tool needs. No case writes a file or runs git.
"""
import json
import os
import unittest
from json.decoder import scanstring

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "..", ".github", "stamp.json")
LIMIT = 3  # an array of more than this many strings is judged


def array_entries(text):
    """{path: [(line, string or None)]}: for each array in the valid JSON `text`, each direct entry with the 1-based line it starts on.
    A string entry gives its text, any other entry (number, literal, array, object) gives None. A path joins object keys with `.`
    and writes an array index as `[i]`: `merge.readyChecks`, `a[0].b`. The top-level value has the path ``."""
    arrays = {}
    stack = []  # open containers: {"kind": "[" or "{", "path": ..., and for an object "key" and "want_key"}
    line, i, size = 1, 0, len(text)
    while i < size:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
        elif ch in " \t\r:":
            i += 1
        elif ch == ",":
            if stack and stack[-1]["kind"] == "{":
                stack[-1]["want_key"] = True
            i += 1
        elif ch in "]}":
            stack.pop()
            i += 1
        else:
            top = stack[-1] if stack else None
            if top is not None and top["kind"] == "{" and top["want_key"]:
                top["key"], i = scanstring(text, i + 1)
                top["want_key"] = False
                continue
            if top is None:
                path = ""
            elif top["kind"] == "[":
                path = "%s[%d]" % (top["path"], len(arrays[top["path"]]))
            else:
                path = top["path"] + "." + top["key"] if top["path"] else top["key"]
            if ch == '"':
                value, end = scanstring(text, i + 1)
            else:
                value, end = None, i + 1
                if ch not in "[{":
                    while end < size and text[end] not in ",]} \t\r\n":
                        end += 1
            if top is not None and top["kind"] == "[":
                arrays[top["path"]].append((line, value))
            if ch == "[":
                arrays[path] = []
                stack.append({"kind": "[", "path": path})
            elif ch == "{":
                stack.append({"kind": "{", "path": path, "key": None, "want_key": True})
            i = end
    return arrays


def parsed_arrays(node, path=""):
    """{path: [string or None]}: the same arrays and paths as array_entries, read from the parsed JSON `node`."""
    found = {}
    if isinstance(node, dict):
        for key, child in node.items():
            found.update(parsed_arrays(child, path + "." + key if path else key))
    elif isinstance(node, list):
        found[path] = [child if isinstance(child, str) else None for child in node]
        for index, child in enumerate(node):
            found.update(parsed_arrays(child, "%s[%d]" % (path, index)))
    return found


def judged(entries):
    """True when the array's entries hold more than LIMIT strings."""
    return sum(1 for _, value in entries if value is not None) > LIMIT


def sharing(entries):
    """(line, first, second): the first two entries that start on one line, or None when each entry has a line of its own."""
    seen = {}
    for line, value in entries:
        if line in seen:
            return line, seen[line], value
        seen[line] = value
    return None


def crowded(text):
    """[(path, line)]: each judged array of `text` that has two entries on one line, in the order the arrays open."""
    found = []
    for path, entries in array_entries(text).items():
        shared = sharing(entries) if judged(entries) else None
        if shared:
            found.append((path, shared[0]))
    return found


def read_config():
    with open(CONFIG_FILE, encoding="utf-8") as handle:
        return handle.read()


def names(count):
    return ["check %d" % n for n in range(count)]


def one_line(items):
    return json.dumps(items)


def per_line(items):
    return "[\n" + ",\n".join("  " + json.dumps(item) for item in items) + "\n]"


# (label, JSON text, [(path, line)] the scan names). Each label states the one claim of its row.
CASES = [
    ("four strings on one line are crowded", '{"a": ["w", "x", "y", "z"]}\n', [("a", 1)]),
    ("three strings on one line are not judged", '{"a": ["w", "x", "y"]}\n', []),
    ("one string per line passes", '{"a": [\n  "w",\n  "x",\n  "y",\n  "z"\n]}\n', []),
    ("two of four strings on one line are crowded", '{"a": [\n  "w",\n  "x", "y",\n  "z"\n]}\n', [("a", 3)]),
    ("the opening bracket's line holding one entry passes", '{"a": ["w",\n  "x",\n  "y",\n  "z"]}\n', []),
    ("empty arrays pass", '{"a": [], "b": [ ], "c": [\n]}\n', []),
    ("five numbers on one line are not strings, so not judged", '{"a": [1, 2, 3, 4, 5]}\n', []),
    ("a nested array is judged on its own strings", '{"a": [["w", "x", "y", "z"]]}\n', [("a[0]", 1)]),
    ("an array in an object in an array carries its whole path", '{"a": [{"b": ["w", "x", "y", "z"]}]}\n', [("a[0].b", 1)]),
    ("an object on one line is not an array", '{"w": "1", "x": "2", "y": "3", "z": "4"}\n', []),
    ("a top-level array is judged", '["w", "x", "y", "z"]\n', [("", 1)]),
    ("literals and numbers are entries: four strings and a literal on one line are crowded",
     '{"a": ["w", "x", "y", "z", true, null, -1.5e3]}\n', [("a", 1)]),
    ("three strings and two numbers are three strings, so not judged", '{"a": ["w", "x", "y", 1, 2]}\n', []),
    ("a literal sharing a line with a string of a judged array is crowded",
     '{"a": [\n  "w",\n  "x",\n  "y",\n  "z", true\n]}\n', [("a", 5)]),
    ("only the crowded array is named", '{"a": ["w", "x", "y", "z"], "b": [\n"w",\n"x",\n"y",\n"z"]}\n', [("a", 1)]),
    ("an array of the same key in another object is its own array",
     '{"x": {"a": ["w", "x", "y", "z"]}, "y": {"a": [\n"w",\n"x",\n"y",\n"z"]}}\n', [("x.a", 1)]),
    # Strings hold the text a line scanner trips on. JSON has no comment and no template literal, so the nearest cases are a
    # comment opener, a bracket, a quote or a newline escape inside a string.
    ("a comma inside an entry does not split it",
     '{"a": [\n  "Retired names, one word per meaning",\n  "x",\n  "y",\n  "z"\n]}\n', []),
    ("a comma inside an entry does not hide a shared line",
     '{"a": ["Retired names, one word per meaning", "x", "y", "z"]}\n', [("a", 1)]),
    ("brackets, braces and comment openers inside entries leave the array whole",
     '{"a": [\n  "[a]",\n  "b]",\n  "{c",\n  "d//e",\n  "f/*g",\n  "h#i"\n]}\n', []),
    ("an escaped quote before a bracket stays inside the string",
     '{"a": [\n  "say \\"hi\\"]",\n  "x",\n  "y",\n  "z"\n]}\n', []),
    ("a lone apostrophe does not open a quote", '{"a": ["don\'t", "x", "y", "z"]}\n', [("a", 1)]),
    ("a string that holds the text of a crowded array is one entry",
     '{"a": ["[\\"w\\", \\"x\\", \\"y\\", \\"z\\"]"]}\n', []),
    ("a key holding a bracket still names its array", '{"k]": ["w", "x", "y", "z"]}\n', [("k]", 1)]),
    ("a newline escape inside a string is not a line break",
     '{"a": [\n  "x\\ny",\n  "p",\n  "q", "r"\n]}\n', [("a", 4)]),
    ("an escaped newline in a string leaves the later line numbers right",
     '{"a": ["x\\ny", "p", "q", "r"],\n "b": ["s", "t", "u", "v"]}\n', [("a", 1), ("b", 2)]),
    ("CRLF line endings count one line each", '{"a": [\r\n"w", "x",\r\n"y",\r\n"z"\r\n]}\r\n', [("a", 2)]),
    ("CRLF with one string per line passes", '{"a": [\r\n"w",\r\n"x",\r\n"y",\r\n"z"\r\n]}\r\n', []),
    ("sixteen strings on one line are crowded", '{"a": %s}\n' % one_line(names(16)), [("a", 1)]),
    ("sixteen strings, one per line, pass", '{"a": %s}\n' % per_line(names(16)), []),
    ("no strings and no array, nothing to judge", "{}\n", []),
]


class TextCases(unittest.TestCase):
    def test_the_scan_names_each_crowded_array_and_no_other(self):
        for label, text, expected in CASES:
            with self.subTest(case=label):
                self.assertEqual(crowded(text), expected)

    def test_the_scan_reads_arrays_as_json_load_reads_them(self):
        for label, text, _ in CASES:
            with self.subTest(case=label):
                scanned = {path: [value for _, value in entries] for path, entries in array_entries(text).items()}
                self.assertEqual(scanned, parsed_arrays(json.loads(text)))


class ConfigFile(unittest.TestCase):
    def arrays(self):
        """{path: entries} of the real file, after the scope check: the scan read each array and each entry as json.load reads them."""
        text = read_config()
        entries = array_entries(text)
        scanned = {path: [value for _, value in found] for path, found in entries.items()}
        self.assertEqual(scanned, parsed_arrays(json.loads(text)), "the scan read the arrays of .github/stamp.json differently from json.load")
        return entries

    def test_the_scan_reads_the_real_file_as_json_load_does(self):
        arrays = self.arrays()
        self.assertTrue(any(judged(found) for found in arrays.values()), "no array of .github/stamp.json holds more than %d strings" % LIMIT)

    def test_the_merge_lists_stay_lists_of_names(self):
        """The merge tool's own rule (parse_config in merge/merge.py): readyChecks is absent or a non-empty list of non-empty strings;
        lintSuites and keepBranches, absent or empty, list nothing, and otherwise hold non-empty strings."""
        merge = json.loads(read_config()).get("merge", {})
        for key, may_be_empty in (("readyChecks", False), ("lintSuites", True), ("keepBranches", True)):
            with self.subTest(list=key):
                items = merge.get(key, [] if may_be_empty else None)
                if items is None:
                    continue
                self.assertIsInstance(items, list)
                self.assertTrue(items or may_be_empty, "merge.%s is empty" % key)
                self.assertTrue(all(isinstance(item, str) and item.strip() for item in items), "merge.%s holds an entry that is no name" % key)

    def test_ready_checks_has_one_name_per_line(self):
        arrays = self.arrays()
        self.assertIn("merge.readyChecks", arrays, ".github/stamp.json holds no merge.readyChecks array, so nothing was judged")
        entries = arrays["merge.readyChecks"]
        self.assertTrue(judged(entries), "merge.readyChecks holds %d names, too few to be judged" % len(entries))
        shared = sharing(entries)
        if shared:
            line, first, second = shared
            self.fail("merge.readyChecks holds %d names; %r and %r share line %d. Put each name on its own line." % (len(entries), first, second, line))

    def test_no_long_array_has_two_strings_on_one_line(self):
        arrays = self.arrays()
        long_arrays = sorted(path for path, found in arrays.items() if judged(found))
        self.assertTrue(long_arrays, "no array of .github/stamp.json holds more than %d strings" % LIMIT)
        for path in long_arrays:
            with self.subTest(array=path):
                shared = sharing(arrays[path])
                if shared:
                    line, first, second = shared
                    self.fail("%s holds %d strings; %r and %r share line %d. Put each string on its own line." % (path, len(arrays[path]), first, second, line))


if __name__ == "__main__":
    unittest.main()
