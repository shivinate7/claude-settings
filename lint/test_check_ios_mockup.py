#!/usr/bin/env python3
"""Cases for lint/check_ios_mockup.py, the iPhone mockup check (roadmap step c192). Standard library only.

    python3 lint/test_check_ios_mockup.py

The checks, on one HTML page:
- system-font: no CSS font-family whose first family is -apple-system or system-ui.
- safe-area: no CSS env(safe-area-inset-...) call.
- duo-frames: no element with data-device="iphone-duo-folded" and one with data-device="iphone-duo-unfolded",
  folded first in document order.
CSS is the text of <style> elements and of style="" attributes. CSS comments are stripped with strings
respected, so a comment opener inside a CSS string is not a comment.

`faults(text)` returns (code, detail) pairs. The CLI prints one `<file>: <code>: <detail>` line per fault and
exits 0 when clean, 1 with faults, and 2 when a file cannot be read. IOS_MOCKUP_UNDER_TEST overrides the script path.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("IOS_MOCKUP_UNDER_TEST") or os.path.join(HERE, "check_ios_mockup.py")
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()

CODES = {"system-font", "safe-area", "duo-frames"}
CSS_OK = ("body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; }\n"
          ".screen { padding: env(safe-area-inset-top) 16px 0; }")
FOLDED = '<section data-device="iphone-duo-folded"><h1>Folded</h1></section>'
UNFOLDED = '<section data-device="iphone-duo-unfolded"><h1>Unfolded</h1></section>'
BODY_OK = "<main>\n" + FOLDED + "\n" + UNFOLDED + "\n</main>"
# A multi-line template literal in a script: its text is not CSS, so the font and inset inside it count for nothing.
TEMPLATE_TRAP = ("const t = `first line\n  body { font-family: -apple-system; }\n  env(safe-area-inset-top)\n"
                 "last line`;")
LINE = re.compile(r"^(?P<file>.+): (?P<code>system-font|safe-area|duo-frames): (?P<detail>.+)$")


def mockup(css=CSS_OK, body=BODY_OK, script=""):
    """A whole page: the CSS in a <style> element, the body, and an optional <script>."""
    tail = "<script>\n%s\n</script>\n" % script if script else ""
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<style>\n%s\n</style>\n</head>\n<body>\n%s\n%s</body>\n</html>\n" % (css, body, tail))


class ModuleCase(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(SCRIPT), "script absent: lint/check_ios_mockup.py")
        spec = importlib.util.spec_from_file_location("check_ios_mockup_under_test", SCRIPT)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def found(self, text):
        checker = getattr(self.m, "faults", None)
        self.assertIsNotNone(checker, "check_ios_mockup must expose faults(text) -> [(code, detail)]")
        return checker(text)

    def codes(self, text):
        return {code for code, _ in self.found(text)}


class Faults(ModuleCase):
    def test_clean_mockup_passes(self):
        self.assertEqual(self.found(mockup()), [])

    def test_missing_system_font_fires_alone(self):
        self.assertEqual(self.codes(mockup(css=CSS_OK.replace("-apple-system, BlinkMacSystemFont, ", ""))),
                         {"system-font"})

    def test_missing_safe_area_fires_alone(self):
        css = "body { font-family: -apple-system, sans-serif; }"
        self.assertEqual(self.codes(mockup(css=css)), {"safe-area"})

    def test_missing_folded_frame_fires_alone(self):
        self.assertEqual(self.codes(mockup(body=UNFOLDED)), {"duo-frames"})

    def test_missing_unfolded_frame_fires_alone(self):
        self.assertEqual(self.codes(mockup(body=FOLDED)), {"duo-frames"})

    def test_unfolded_frame_before_folded_fires_duo_frames(self):
        self.assertEqual(self.codes(mockup(body=UNFOLDED + "\n" + FOLDED)), {"duo-frames"})

    def test_first_family_must_be_the_system_font(self):
        css = "body { font-family: Inter, -apple-system, sans-serif; }\n.screen { padding: env(safe-area-inset-top); }"
        self.assertEqual(self.codes(mockup(css=css)), {"system-font"})

    def test_system_ui_as_first_family_passes(self):
        css = "body { font-family: system-ui, sans-serif; }\n.screen { padding: env(safe-area-inset-top); }"
        self.assertEqual(self.found(mockup(css=css)), [])

    def test_system_font_in_font_shorthand_passes(self):
        css = "body { font: 600 17px/1.3 -apple-system, sans-serif; }\n.screen { padding: env(safe-area-inset-top); }"
        self.assertEqual(self.found(mockup(css=css)), [])

    def test_system_font_through_a_custom_property_passes(self):
        css = (":root { --font: -apple-system, sans-serif; }\nbody { font-family: var(--font); }\n"
               ".screen { padding: env(safe-area-inset-top); }")
        self.assertEqual(self.found(mockup(css=css)), [])

    def test_dynamic_type_keyword_in_font_shorthand_passes(self):
        css = "body { font: -apple-system-body; }\n.screen { padding: env(safe-area-inset-top); }"
        self.assertEqual(self.found(mockup(css=css)), [])

    def test_important_after_system_font_passes(self):
        css = "body { font-family: -apple-system !important; }\n.screen { padding: env(safe-area-inset-top); }"
        self.assertEqual(self.found(mockup(css=css)), [])

    def test_georgia_in_font_shorthand_fires_system_font_alone(self):
        css = "body { font: 600 17px/1.3 Georgia, serif; }\n.screen { padding: env(safe-area-inset-top); }"
        self.assertEqual(self.codes(mockup(css=css)), {"system-font"})

    def test_georgia_through_a_custom_property_fires_system_font_alone(self):
        css = (":root { --font: Georgia, serif; }\nbody { font-family: var(--font); }\n"
               ".screen { padding: env(safe-area-inset-top); }")
        self.assertEqual(self.codes(mockup(css=css)), {"system-font"})

    def test_font_and_safe_area_in_style_attributes_count(self):
        body = ('<main style="font-family: -apple-system, sans-serif; padding: env(safe-area-inset-top);">\n'
                + FOLDED + "\n" + UNFOLDED + "\n</main>")
        self.assertEqual(self.found(mockup(css="", body=body)), [])

    def test_system_font_only_in_a_css_comment_is_missing(self):
        css = "/* body { font-family: -apple-system, sans-serif; } */\n.screen { padding: env(safe-area-inset-top); }"
        self.assertEqual(self.codes(mockup(css=css)), {"system-font"})

    def test_comment_opener_inside_a_css_string_hides_nothing(self):
        for opener in ('content: "/*";', 'background: url("http://a.test/x.png");', 'content: "# not a comment";'):
            with self.subTest(opener=opener):
                css = (".badge::before { %s } body { font-family: -apple-system, sans-serif; } "
                       ".screen { padding: env(safe-area-inset-top); }" % opener)
                self.assertEqual(self.found(mockup(css=css)), [])

    def test_safe_area_only_in_a_script_string_is_missing(self):
        css = "body { font-family: -apple-system, sans-serif; }"
        self.assertEqual(self.codes(mockup(css=css, script='const s = "env(safe-area-inset-top)";')), {"safe-area"})

    def test_frames_only_in_an_html_comment_are_missing(self):
        self.assertEqual(self.codes(mockup(body="<!-- " + BODY_OK + " -->")), {"duo-frames"})

    def test_multiline_template_literal_in_a_script_is_not_css(self):
        css = "body { font: 16px sans-serif; }"
        self.assertEqual(self.codes(mockup(css=css, script=TEMPLATE_TRAP)), {"system-font", "safe-area"})

    def test_multiline_template_literal_alone_is_clean(self):
        self.assertEqual(self.found(mockup(script=TEMPLATE_TRAP)), [])

    def test_lone_quote_in_text_is_clean(self):
        self.assertEqual(self.found(mockup(body=BODY_OK + "\n<p>Don't</p>")), [])


class Cli(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(SCRIPT), "script absent: lint/check_ios_mockup.py")
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)

    def page(self, name, text):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def run_cli(self, *paths):
        return subprocess.run([sys.executable, SCRIPT] + list(paths), capture_output=True, text=True, timeout=60)

    def test_clean_file_exits_0(self):
        done = self.run_cli(self.page("clean.html", mockup()))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_each_fault_is_one_line_naming_file_code_and_detail(self):
        path = self.page("bad.html", mockup(css="body { font-family: Inter; }", body="<p>No frames.</p>"))
        done = self.run_cli(path)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 3, done.stdout)
        matched = [LINE.match(line) for line in lines]
        self.assertTrue(all(matched), done.stdout)
        self.assertEqual({m.group("code") for m in matched}, CODES, done.stdout)
        self.assertTrue(all(os.path.basename(path) in m.group("file") for m in matched), done.stdout)

    def test_only_the_bad_file_is_named(self):
        good = self.page("good.html", mockup())
        bad = self.page("bad.html", mockup(body=UNFOLDED + "\n" + FOLDED))
        done = self.run_cli(good, bad)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, done.stdout)
        self.assertIn("bad.html", lines[0])
        self.assertIn("duo-frames", lines[0])

    def test_unreadable_file_exits_2(self):
        done = self.run_cli(os.path.join(self.folder, "no-such-page.html"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
