"""Fixture suite for field_table.py, the item field table of SKILL.md. Run: python3 skills/waiting-page/test_field_table.py

    field_table.py --check    exit 0 and no output when the block is current; else exit 1 and the stale block
    field_table.py            writes the block; refused (exit 1, nothing written) while a problem stands

Every case passes --skill, --page and --data. A case that writes works on temp copies of the three real files,
and the real files are read and never written. The real files are also the full-size fixture.

FIELD_TABLE_UNDER_TEST names the script to run (default: field_table.py beside this file), so the same cases run
red against a mutant of it. The rows are read by an oracle written here with html.parser, so the script's own
reader is not its own oracle. Temp files: the run folder of lint/_test_temp.py; its sweep is proved in
lint/test_find_copies.py.
"""
import html.parser
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
REAL = {name: os.path.join(HERE, name) for name in ("SKILL.md", "page.html", "field_table.json")}
OPEN, CLOSE = "<!-- gen:item-fields -->", "<!-- /gen -->"
ITEM_FIELDS = '<script type="application/json" id="itemFields">'
DECOY = '["decoy"]'
# Decoys that only a reader which takes script text as data passes over. The `<\/script>` does not end the script.
JS_STRING = "<script>\nconst D = '" + ITEM_FIELDS + DECOY + "<\\/script>';\n</script>"
JS_TEMPLATE = "<script>\nconst T = `\n" + ITEM_FIELDS + DECOY + "<\\/script>\n`;\n</script>"
FENCED = "\n```\n" + OPEN + "\n" + CLOSE + "\n```\n"
RUN_FOLDER = None  # made in setUpModule


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


class ItemFieldList(html.parser.HTMLParser):
    """The text of the first script whose id is itemFields. Comments and script text are data, not tags."""

    def __init__(self):
        super().__init__()
        self.inside, self.seen, self.parts = False, False, []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not self.seen and dict(attrs).get("id") == "itemFields":
            self.inside, self.seen = True, True

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False


def page_fields(text):
    """The page's field list, read by ItemFieldList."""
    reader = ItemFieldList()
    reader.feed(text)
    reader.close()
    return json.loads("".join(reader.parts))


def block_rows(text):
    """The field names of SKILL.md's block: the first cell of each row that starts with a backticked name."""
    rows, inside = [], False
    for line in text.split("\n"):
        s = line.strip()
        if s == OPEN:
            inside = True
        elif s == CLOSE:
            break
        elif inside and s.startswith("| `"):
            rows.append(s[3:s.index("`", 3)])
    return rows


def block_text(text):
    """The block as the file holds it, markers and indentation included. None unless there is exactly one."""
    lines = text.split("\n")
    opens = [i for i, line in enumerate(lines) if line.strip() == OPEN]
    closes = [i for i, line in enumerate(lines) if line.strip() == CLOSE]
    if len(opens) != 1 or len(closes) != 1 or opens[0] > closes[0]:
        return None
    return "\n".join(lines[opens[0]:closes[0] + 1])


class Copies(unittest.TestCase):
    """Temp copies of the three real files, in a folder of this run: self.skill, self.page and self.data."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.addCleanup(self.tmp.cleanup)
        self.reset()

    def reset(self):
        self.skill = self.put("SKILL.md", read(REAL["SKILL.md"]))
        self.page = self.put("page.html", read(REAL["page.html"]))
        self.data = self.put("field_table.json", read(REAL["field_table.json"]))

    def put(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return path

    def run_script(self, *args, skill=None, page=None, data=None):
        cmd = [sys.executable, CMD, "--skill", skill or self.skill, "--page", page or self.page,
               "--data", data or self.data, *args]
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8")
        return r.returncode, r.stdout, r.stderr

    def real_fields(self):
        fields = page_fields(read(REAL["page.html"]))
        self.assertTrue(fields, "fixture: the real page's itemFields list reads empty")  # scope before subject (P7)
        return fields

    def page_with(self, fields):
        """The real page with its itemFields list replaced by `fields`."""
        text = read(REAL["page.html"])
        old = ITEM_FIELDS + json.dumps(page_fields(text)) + "</script>"
        self.assertEqual(text.count(old), 1, "fixture: the real page's itemFields script is not in the form read here")
        return text.replace(old, ITEM_FIELDS + json.dumps(fields) + "</script>")

    def page_with_decoy(self, markup):
        """The real page with `markup` placed ahead of its real itemFields script."""
        text = read(REAL["page.html"])
        self.assertEqual(text.count(ITEM_FIELDS), 1, "fixture: the real page has no single itemFields script")
        return text.replace(ITEM_FIELDS, markup + "\n" + ITEM_FIELDS, 1)

    def data_with(self, change):
        """The real data with `change(data)` applied, as the text to write."""
        data = json.loads(read(REAL["field_table.json"]))
        change(data)
        return json.dumps(data, indent=2)

    def skill_row(self, text, field):
        """The one table row of `field` in SKILL.md text, indentation kept."""
        rows = [line for line in text.split("\n") if line.strip().startswith("| `%s` |" % field)]
        self.assertEqual(len(rows), 1, "fixture: %d table rows for %s in SKILL.md" % (len(rows), field))
        return rows[0]

    def edited_row(self, text, field):
        """`text` with the meaning of `field`'s row changed, so the block is stale."""
        row = self.skill_row(text, field)
        return text.replace(row, row.rstrip()[:-1].rstrip() + " EDITED |")

    def assertProblem(self, result, line, why):
        code, out, err = result
        self.assertNotIn("Traceback", err, why + ": the script crashed instead of naming the problem")
        self.assertEqual(code, 1, why + ": exit %d, want 1; said: %s" % (code, out + err))
        self.assertIn(line, out, why + ": the problem is not named")


class RealRepo(unittest.TestCase):
    """The real files, only read: --check never writes."""

    def test_check_on_the_real_repo_is_clean(self):
        flags = ["--skill", REAL["SKILL.md"], "--page", REAL["page.html"], "--data", REAL["field_table.json"]]
        r = subprocess.run([sys.executable, CMD, "--check", *flags], capture_output=True, encoding="utf-8")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), "--check on the real repo is not clean")

    def test_rows_are_the_page_item_fields_in_order(self):
        fields = page_fields(read(REAL["page.html"]))
        self.assertTrue(fields, "fixture: the real page's itemFields list reads empty")  # scope before subject (P7)
        self.assertEqual(block_rows(read(REAL["SKILL.md"])), fields, "the table rows are not the page's itemFields in order")


class Check(Copies):
    def assert_stale(self, after):
        """--check on `after` (the block is stale): exit 1, the stale block printed as the file holds it, no write."""
        self.assertIsNotNone(block_text(after), "fixture: the stale SKILL.md has no single block")
        code, out, err = self.run_script("--check")
        self.assertEqual(code, 1, "a stale block: exit %d, want 1; said: %s" % (code, out + err))
        self.assertIn("stale:", out, "the check does not say the block is stale")
        self.assertIn(block_text(after), out, "the stale block as the file holds it is not printed")
        self.assertEqual(read(self.skill), after, "--check wrote the file")

    def test_copies_of_the_real_files_are_clean(self):
        code, out, err = self.run_script("--check")
        self.assertEqual((code, out, err), (0, "", ""), "a copy of the real files is not clean under --check")

    def test_edited_cell_is_stale_and_the_block_is_printed(self):
        after = self.edited_row(read(self.skill), "n")
        self.put("SKILL.md", after)
        self.assert_stale(after)

    def test_deleted_row_is_stale_and_the_block_is_printed(self):
        before = read(self.skill)
        after = before.replace(self.skill_row(before, "ref") + "\n", "")
        self.put("SKILL.md", after)
        self.assert_stale(after)

    def test_page_field_with_no_data_entry_is_a_problem(self):
        self.put("page.html", self.page_with(self.real_fields() + ["zzz"]))
        self.assertProblem(self.run_script("--check"),
                           "field zzz is in itemFields and has no entry in the data file", "a page field with no data entry")

    def test_data_field_not_on_the_page_is_a_problem(self):
        def add_ghost(data):
            data["ghost"] = {"meaning": "A field the page does not list."}
        self.put("field_table.json", self.data_with(add_ghost))
        self.assertProblem(self.run_script("--check"),
                           "field ghost is in the data file and not in itemFields", "a data field the page does not list")

    def test_rule_not_in_page_reasons_is_a_problem(self):
        def add_rule(data):
            data["kind"]["rules"].append("no-such-rule")
        self.put("field_table.json", self.data_with(add_rule))
        self.assertProblem(self.run_script("--check"),
                           "field kind names rule no-such-rule, which is not in PAGE_REASONS", "a rule the guard does not hold")

    def test_empty_meaning_is_a_problem(self):
        def blank(data):
            data["id"]["meaning"] = ""
        self.put("field_table.json", self.data_with(blank))
        self.assertProblem(self.run_script("--check"), "field id has no meaning", "an empty meaning")

    def test_decoy_block_in_an_html_comment_is_ignored(self):
        self.put("page.html", self.page_with_decoy("<!-- " + ITEM_FIELDS + DECOY + "</script> -->"))
        code, out, err = self.run_script("--check")
        self.assertEqual((code, out, err), (0, "", ""), "a decoy inside an HTML comment was read as the field list")

    def test_decoy_in_a_script_string_or_template_literal_is_ignored(self):
        for why, markup in (("a string", JS_STRING), ("a template literal", JS_TEMPLATE)):
            with self.subTest(why):
                self.put("page.html", self.page_with_decoy(markup))
                code, out, err = self.run_script("--check")
                self.assertEqual((code, out, err), (0, "", ""), "a decoy inside %s in a script was read as the field list" % why)

    def test_the_same_decoy_as_markup_is_read(self):
        # Control: the decoy as markup is read, so the three decoy cases above can fail.
        self.put("page.html", self.page_with_decoy(ITEM_FIELDS + DECOY + "</script>"))
        self.assertProblem(self.run_script("--check"),
                           "field decoy is in itemFields and has no entry in the data file", "a decoy written as markup")

    def test_marker_in_a_code_fence_is_not_a_block(self):
        self.put("SKILL.md", read(self.skill) + FENCED)
        code, out, err = self.run_script("--check")
        self.assertEqual((code, out, err), (0, "", ""), "a marker inside a code fence was counted as a block")

    def test_marker_inside_a_sentence_is_not_a_block(self):
        text = read(self.skill)
        sentence = "Write `%s` by hand; don't edit `/*`, `//` or `#` here.\n" % OPEN
        self.put("SKILL.md", text.replace(block_text(text), sentence + block_text(text), 1))
        code, out, err = self.run_script("--check")
        self.assertEqual((code, out, err), (0, "", ""), "a marker inside a sentence, or a lone quote, broke the block read")

    def test_missing_skill_is_exit_2(self):
        code, out, err = self.run_script("--check", skill=os.path.join(self.tmp.name, "absent.md"))
        self.assertEqual(code, 2, "a missing SKILL.md: exit %d, want 2; said: %s" % (code, out + err))
        self.assertIn("cannot read", err, "a missing SKILL.md is not named as unreadable")

    def test_doubled_block_is_exit_2(self):
        text = read(self.skill)
        doubled = text + "\n" + block_text(text) + "\n"
        self.put("SKILL.md", doubled)
        code, out, err = self.run_script("--check")
        self.assertEqual(code, 2, "a doubled block: exit %d, want 2; said: %s" % (code, out + err))
        self.assertIn("has not exactly one", err, "a doubled block is not named")

    def test_no_block_is_exit_2(self):
        text = read(self.skill)
        self.put("SKILL.md", text.replace(block_text(text), ""))
        code, out, err = self.run_script("--check")
        self.assertEqual(code, 2, "no block: exit %d, want 2; said: %s" % (code, out + err))
        self.assertIn("has not exactly one", err, "a missing block is not named")


class Write(Copies):
    def test_write_repairs_a_stale_block_and_keeps_every_other_byte(self):
        real = read(REAL["SKILL.md"])
        prefix = "Café — naïve: text outside the block.\n\n"
        self.put("SKILL.md", prefix + self.edited_row(real, "n"))
        code, out, err = self.run_script()
        self.assertEqual((code, out, err), (0, "", ""), "the write did not run clean")
        self.assertEqual(read(self.skill), prefix + real, "the write changed a byte outside the block, or left the block stale")
        self.assertEqual(self.run_script("--check")[0], 0, "the written file is not current")

    def test_write_keeps_crlf_line_endings_outside_the_block(self):
        real = read(REAL["SKILL.md"])
        self.put("SKILL.md", self.edited_row(real, "n").replace("\n", "\r\n"))
        code, out, err = self.run_script()
        self.assertEqual(code, 0, "the write did not run clean on a CRLF file: " + out + err)
        self.assertEqual(read(self.skill), real.replace("\n", "\r\n"), "the write changed the line endings outside the block")

    def test_write_repairs_the_block_and_keeps_a_fenced_marker(self):
        real = read(REAL["SKILL.md"])
        self.put("SKILL.md", self.edited_row(real, "n") + FENCED)
        code, out, err = self.run_script()
        self.assertEqual(code, 0, "the write did not run clean beside a fenced marker: " + out + err)
        self.assertEqual(read(self.skill), real + FENCED, "the write changed the fenced text, or left the block stale")

    def test_write_is_refused_while_a_problem_stands(self):
        stale = self.edited_row(read(REAL["SKILL.md"]), "n")
        cases = (
            ("an empty meaning", "field_table.json", self.data_with(lambda d: d["id"].update(meaning="")),
             "field id has no meaning"),
            ("a page field with no data entry", "page.html", self.page_with(self.real_fields() + ["zzz"]),
             "field zzz is in itemFields and has no entry in the data file"),
        )
        for why, name, text, line in cases:
            with self.subTest(why):
                self.reset()
                self.put("SKILL.md", stale)
                self.put(name, text)
                self.assertProblem(self.run_script(), line, why)
                self.assertEqual(read(self.skill), stale, why + ": the write changed the SKILL.md block")

    def test_pipe_in_a_meaning_is_escaped(self):
        self.put("field_table.json", self.data_with(lambda d: d["id"].update(meaning="Same | string as the database key.")))
        code, out, err = self.run_script()
        self.assertEqual(code, 0, "the write refused a pipe in a meaning: " + out + err)
        row = self.skill_row(read(self.skill), "id")
        self.assertIn("Same \\| string as the database key.", row, "the pipe in the meaning is not escaped")
        self.assertEqual(len(re.split(r"(?<!\\)\|", row.strip())), 5, "a pipe in the meaning splits the row into more cells")
        self.assertEqual(self.run_script("--check")[0], 0, "the written file is not current")

    def test_rows_follow_the_page_order(self):
        reversed_fields = list(reversed(self.real_fields()))
        self.put("page.html", self.page_with(reversed_fields))
        code, out, err = self.run_script()
        self.assertEqual(code, 0, "the write did not run clean with a reordered page: " + out + err)
        self.assertEqual(block_rows(read(self.skill)), reversed_fields, "the rows do not follow the page's itemFields order")
        self.assertEqual(self.run_script("--check")[0], 0, "the written file is not current")

    def test_empty_item_fields_list_does_not_read(self):
        self.put("page.html", self.page_with([]))
        self.assertProblem(self.run_script("--check"), "itemFields block of the page does not read", "an empty itemFields list")

    def test_empty_data_flags_every_field(self):
        fields = self.real_fields()
        self.put("field_table.json", "{}")
        code, out, err = self.run_script("--check")
        self.assertEqual(code, 1, "an empty data file: exit %d, want 1; said: %s" % (code, out + err))
        flagged = [line for line in out.splitlines() if line.endswith("has no entry in the data file")]
        self.assertEqual(len(flagged), len(fields), "an empty data file does not flag every field")


if __name__ == "__main__":
    unittest.main()
