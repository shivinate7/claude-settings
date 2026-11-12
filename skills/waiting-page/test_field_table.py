"""Fixture suite for field_table.py. Run: python3 skills/waiting-page/test_field_table.py

Each case builds its SKILL.md, page and data file in one run folder (lint/_test_temp.py) from the real page's
itemFields list; only the real-repo case reads the real files. FIELD_TABLE_UNDER_TEST names the script to run.
"""
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
import _test_temp  # noqa: E402

CMD = os.environ.get("FIELD_TABLE_UNDER_TEST") or os.path.join(HERE, "field_table.py")
REAL = {n: os.path.join(HERE, n) for n in ("SKILL.md", "page.html", "field_table.json")}
OPEN, CLOSE = "<!-- gen:item-fields -->", "<!-- /gen -->"
ITEM = '<script type="application/json" id="itemFields">'
DECOY = ITEM + '["decoy"]</script>'
ESC = DECOY.replace("</script>", "<\\/script>")  # `<\/script>` does not end a script
DECOYS = {"an HTML comment": "<!-- " + DECOY + " -->", "a string": "<script>const D = '" + ESC + "';</script>",
          "a template literal": "<script>const T = `\n" + ESC + "\n`;</script>"}
SENTENCE = "Write `%s` by hand; don't edit `/*`, `//` or `#` here." % OPEN
FENCED = "\n```\n" + OPEN + "\n" + CLOSE + "\n```\n"
SKILL_EMPTY = "Intro line.\n\n  " + OPEN + "\n  " + CLOSE + "\n\nOutro line.\n"
BLOCK = re.compile(r"(?ms)^[ \t]*%s[ \t]*\r?$.*?^[ \t]*%s[ \t]*\r?$" % (re.escape(OPEN), re.escape(CLOSE)))
ROW = re.compile(r"(?m)^[ \t]*\| `([^`]+)` \|")
RUN_FOLDER = _test_temp.run_folder()  # one run folder per run, removed when the run ends
atexit.register(shutil.rmtree, RUN_FOLDER, True)


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


FIELDS = json.loads(re.search(r'id="itemFields">(.*?)</script>', read(REAL["page.html"]), re.S).group(1))


def block_of(text):
    found = BLOCK.findall(text)
    return found[0] if len(found) == 1 else None


def block_rows(text):
    return ROW.findall(block_of(text) or "")


def data_for(change=None):
    data = {f: {"meaning": "What %s holds." % f, "rules": []} for f in FIELDS}
    data["port"]["rules"] = ["port-question"]
    (change or (lambda d: None))(data)
    return json.dumps(data, indent=2)


def edit_meaning(text, field):
    """`text` with the meaning of `field`'s row changed, so the block is stale. CRLF-safe."""
    return re.sub(r"(?m)^([ \t]*\| `%s` \|.*?) \|(\r?)$" % re.escape(field),
                  lambda m: m.group(1) + " EDITED |" + m.group(2), text, count=1)


class Cases(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.skill, self.page = self.put("SKILL.md", SKILL_EMPTY), self.put("page.html", read(REAL["page.html"]))
        self.data = self.put("field_table.json", data_for())
        self.expect(0, "fixture: the baseline block was not written")
        self.baseline = read(self.skill)

    def put(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return os.path.join(self.dir, name)

    def run_cmd(self, *args):
        flags = ["--skill", self.skill, "--page", self.page, "--data", self.data]
        r = subprocess.run([sys.executable, CMD, *flags, *args], capture_output=True, encoding="utf-8")
        return r.returncode, r.stdout, r.stderr

    def expect(self, want, why, *args):
        code, out, err = self.run_cmd(*args)
        self.assertEqual(code, want, "%s: exit %d, want %d: %s" % (why, code, want, out + err))
        return out, err

    def page_with(self, fields, markup=""):
        old, text = ITEM + json.dumps(FIELDS) + "</script>", read(REAL["page.html"])
        self.assertEqual(text.count(old), 1, "fixture: the real page's itemFields script is not in the form read here")
        return text.replace(old, (markup + "\n" if markup else "") + ITEM + json.dumps(fields) + "</script>")

    def assert_problem(self, tokens, why):
        """Exit 1 in --check and in write mode, one stdout line naming each token, SKILL.md unchanged."""
        before = read(self.skill)
        for args in (("--check",), ()):
            with self.subTest(mode=args):
                out, _ = self.expect(1, why, *args)
                self.assertEqual(len(out.splitlines()), 1, "%s: want one problem line, got %r" % (why, out))
                self.assertTrue(all(re.search(r"\b%s\b" % re.escape(t), out) for t in tokens), "%s: no name" % why)
                self.assertEqual(read(self.skill), before, "%s: SKILL.md was written" % why)

    def test_written_block_is_current_and_shaped(self):
        self.assertEqual(self.run_cmd("--check"), (0, "", ""), "a block the script just wrote is not current")
        block = block_of(self.baseline)
        self.assertIn("| Field | Guard rules | Meaning |", block, "the table header is missing")
        self.assertIn("`item-field-rendered`", block, "no line names the rule item-field-rendered")
        self.assertTrue(all(l.startswith("  ") for l in block.split("\n") if l), "a block line lacks the indent")
        self.assertEqual(block_rows(self.baseline), FIELDS, "the rows are not the page's itemFields in order")

    def test_stale_cell_and_deleted_row_print_the_block(self):
        deleted = "\n".join(line for line in self.baseline.split("\n") if "| `ref` |" not in line)
        for why, after in (("a stale cell", edit_meaning(self.baseline, "n")), ("a deleted row", deleted)):
            with self.subTest(why):
                self.put("SKILL.md", after)
                out, _ = self.expect(1, why, "--check")
                self.assertIn(block_of(after), out, "%s: the block is not printed as the file holds it" % why)
                self.assertEqual(read(self.skill), after, "%s: --check wrote SKILL.md" % why)

    def test_each_problem_is_named_and_refused(self):
        cases = (("a page field with no data entry", FIELDS + ["zzz"], None, ("zzz",)),
                 ("a data field the page does not list", None,
                  lambda d: d.update(ghost={"meaning": "Not on the page.", "rules": []}), ("ghost",)),
                 ("an empty meaning", None, lambda d: d["id"].update(meaning=""), ("id",)),
                 ("a rule PAGE_REASONS does not hold", None, lambda d: d["kind"].update(rules=["no-such-rule"]),
                  ("kind", "no-such-rule")))
        for why, fields, change, tokens in cases:
            with self.subTest(why):
                self.put("page.html", self.page_with(fields) if fields else read(REAL["page.html"]))
                self.put("field_table.json", data_for(change))
                self.assert_problem(tokens, why)

    def test_empty_item_fields_list_does_not_read(self):
        self.put("page.html", self.page_with([]))
        for args in (("--check",), ()):
            with self.subTest(mode=args):
                code, out, err = self.run_cmd(*args)
                self.assertTrue(code and "Traceback" not in err, "an empty itemFields list: exit %d: %s" % (code, err))
                self.assertIn("itemFields", out + err, "the empty itemFields list is not named")
                self.assertEqual(read(self.skill), self.baseline, "an empty itemFields list wrote SKILL.md")

    def test_doubled_or_missing_block_is_exit_2(self):
        block = block_of(self.baseline)
        cases = (("doubled", self.baseline + "\n" + block + "\n"), ("missing", self.baseline.replace(block, "")))
        for why, text in cases:
            self.put("SKILL.md", text)
            for args in (("--check",), ()):
                _, err = self.expect(2, "a %s block" % why, *args)
                self.assertIn("SKILL.md", err, "a %s block is not named on stderr" % why)
            self.assertEqual(read(self.skill), text, "a %s block: SKILL.md was written" % why)

    def test_decoys_are_not_read(self):
        skill = (("a code fence", self.baseline + FENCED), ("a sentence", SENTENCE + "\n" + self.baseline))
        for why, text in skill:
            with self.subTest(why):
                self.put("SKILL.md", text)
                self.assertEqual(self.run_cmd("--check"), (0, "", ""), "a marker in %s was read as a block" % why)
        for why, markup in DECOYS.items():
            with self.subTest(why):
                self.put("page.html", self.page_with(FIELDS, markup))
                self.assertEqual(self.run_cmd("--check"), (0, "", ""), "a decoy in %s was read as the field list" % why)
        # Control: the decoy as markup is read, so the cases above can fail.
        self.put("page.html", self.page_with(FIELDS, DECOY))
        out, _ = self.expect(1, "a decoy written as markup")
        self.assertIn("decoy", out, "a decoy written as markup is not read")

    def test_write_keeps_every_other_byte_and_crlf(self):
        prefix = "Café — naïve: text outside the block.\n\n"
        self.put("SKILL.md", prefix + edit_meaning(self.baseline, "n"))
        self.expect(0, "a stale block")
        self.assertEqual(read(self.skill), prefix + self.baseline, "the write changed a byte outside the block")
        self.put("SKILL.md", edit_meaning(self.baseline, "n").replace("\n", "\r\n"))
        self.expect(0, "a CRLF file")
        self.assertEqual(read(self.skill), self.baseline.replace("\n", "\r\n"), "the write changed the line endings")

    def test_pipe_in_a_meaning_is_escaped(self):
        self.put("field_table.json", data_for(lambda d: d["id"].update(meaning="Same | string as the database key.")))
        self.expect(0, "a pipe in a meaning")
        row = [line for line in block_of(read(self.skill)).split("\n") if "| `id` |" in line]
        self.assertEqual(len(row), 1, "the id row is not one line")
        self.assertIn("Same \\| string as the database key.", row[0], "the pipe in the meaning is not escaped")
        self.assertEqual(len(re.split(r"(?<!\\)\|", row[0].strip())), 5, "a pipe in the meaning splits the row")

    def test_rows_follow_the_page_order(self):
        self.put("page.html", self.page_with(FIELDS[::-1]))
        self.expect(0, "a reordered page")
        self.assertEqual(block_rows(read(self.skill)), FIELDS[::-1], "the rows do not follow the page's order")


class RealRepo(unittest.TestCase):
    def test_check_on_the_real_repo_is_clean(self):
        flags = ["--skill", REAL["SKILL.md"], "--page", REAL["page.html"], "--data", REAL["field_table.json"]]
        r = subprocess.run([sys.executable, CMD, "--check", *flags], capture_output=True, encoding="utf-8")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), "--check on the real files is not clean")


if __name__ == "__main__":
    unittest.main()
