#!/usr/bin/env python3
"""Cases for hooks/blind_brief.py, the blind design brief check. Standard library only.

Run it from the repository root:

    python3 hooks/test_blind_brief.py

Contract (the module's own docstring):
- `brief_faults(text, current=())` lists the faults of one blind brief. A clean brief has none.
  A brief must follow skills/design-explore/blind-brief.md: a `Lane kind: blind` line, a `Lane:` line,
  the free sections Job and Device, and the fixed sections House rules and Deliver word for word. A
  free section may not name the current product, a screenshot or mockup, a path or link, the spec or
  tokens, or a keep or match rule, and holds no colour, font or spacing value. A Palette section, or any
  other colour, font or spacing section, is refused. `current` names views of today's product, refused as words.
- `run_faults(texts, owner_none="")` lists the faults of one explore run: a brief with no kind line,
  each blind brief's faults, and a run with no blind lane unless the owner's words for none are given.
- `--run DIR` checks every *.md brief in DIR: exit 0 clean, 1 with one line per fault, 2 unreadable.
- As a PreToolUse hook on Agent and Task, a designer spawn is judged by its brief. A blind brief with
  a fault, or an informed or directed brief with no `Blind lanes:` line of 1 or more (or `none` with
  the owner's quoted words), is refused with rule `blind-brief`. Any other spawn passes. Junk input
  passes with no output.

The Duo brief below is the incident of decision blind-briefs-use-a-template. Its four
sentences are the ones the orchestrator quoted from its own brief. It is the red-first fixture.

Override the module under test with the env var BLIND_BRIEF_UNDER_TEST.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("BLIND_BRIEF_UNDER_TEST") or os.path.join(HERE, "blind_brief.py")
TEMPLATE = os.path.join(HERE, "..", "skills", "design-explore", "blind-brief.md")
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()


def load():
    spec = importlib.util.spec_from_file_location("blind_brief_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DUO_BRIEF = """Design the MANIFEST screens for the iPhone Duo's large fold.
Duo layouts must keep that look.
Look at the web app first, to see what the owner wants matched.
Draw 2 or 3 two-page options for each existing view (Packages, Tally, Orphaned).
Hold every variable constant except one.
"""

JOB = """Shiv buys hundreds of cheap trading cards from many sellers. On mail day he opens the
mailbox, matches each envelope to what he bought, and checks each card off. In his words: "did all
four arrive", and "what is still out, and what did it all cost". He also wants to keep track of
mail that may be lost.

The things the job handles: orders (seller, date, cost), the cards in each order (name, set,
count), and envelopes that arrive with no sender. A busy day holds 40 envelopes and 300 cards."""

DEVICE = """A folding phone with two 5.8 inch screens and a hinge between them. Poses: open as a
book, folded as a tent on a desk, one screen alone, and a small outer screen when closed. Touch
only."""

# The d4 incident (roadmap step c191): the blind brief carried a brand palette, and the designer's notes
# said "Banchi blue #3d5af1", the hex of banchi's entry in docs/design/repo-colours.json.
PALETTE = "Banchi blue #3d5af1, ink #14161f, surface #f6f7fb."
FONTS = "Headings in Inter 600, body in system-ui, mono in JetBrains Mono."
SPACING = "Spacing uses a 4 px step, cards have 12 px padding and an 8 px radius."


def fixed(name):
    """The fixed section `name` of the template, its body as written there."""
    with open(TEMPLATE, encoding="utf-8") as handle:
        text = handle.read()
    head = "## " + name + "\n"
    body = text.split(head, 1)[1]
    return body.split("\n## ", 1)[0].strip()


def brief(job=JOB, device=DEVICE, palette=None, header="Lane kind: blind\nLane: packages-blind-1",
          extra=""):
    return "\n".join([
        header, "",
        "## Job", job, "",
        "## Device", device, "",
        "## Palette\n" + palette + "\n" if palette is not None else "",
        "## House rules", fixed("House rules"), "",
        "## Deliver", fixed("Deliver"), "",
        extra,
    ])


def codes(faults):
    return {f[0] for f in faults}


class BriefFaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_clean_brief_passes(self):
        self.assertEqual(self.m.brief_faults(brief()), [])

    def test_clean_brief_with_match_and_keep_track_in_the_job_passes(self):
        # "matches each envelope" and "keep track of mail" are the owner's job words, not rules.
        self.assertEqual(self.m.brief_faults(brief(), current=("Tally", "Orphaned")), [])

    def test_template_filled_passes(self):
        with open(TEMPLATE, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace("<screen>-blind-<n>", "packages-blind-1")
        for name, body in (("Job", JOB), ("Device", DEVICE)):
            head = "## " + name + "\n"
            start = text.index(head) + len(head)
            end = text.index("\n## ", start)
            text = text[:start] + body + "\n" + text[end:]
        self.assertEqual(self.m.brief_faults(text), [])

    def test_unfilled_template_is_refused(self):
        with open(TEMPLATE, encoding="utf-8") as handle:
            self.assertIn("placeholder", codes(self.m.brief_faults(handle.read())))

    def test_duo_brief_is_refused(self):
        found = codes(self.m.brief_faults("Lane kind: blind\nLane: duo-blind-1\n\n" + DUO_BRIEF))
        self.assertTrue({"outside", "section-missing"} <= found, found)

    def test_duo_keep_rule_is_refused(self):
        self.assertIn("keep", codes(self.m.brief_faults(brief(job=JOB + "\nDuo layouts must keep that look."))))

    def test_duo_web_app_first_is_refused(self):
        line = "Look at the web app first, to see what the owner wants matched."
        self.assertIn("current", codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_duo_existing_view_is_refused(self):
        line = "Draw 2 or 3 two-page options for each existing view (Packages, Tally, Orphaned)."
        self.assertIn("current", codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_named_current_view_is_refused(self):
        found = self.m.brief_faults(brief(job=JOB + "\nPut Tally on the left page."), current=("Tally",))
        self.assertIn("named-view", codes(found))

    def test_named_view_matches_whole_words_only(self):
        self.assertEqual(self.m.brief_faults(brief(job=JOB + "\nA tally of cards."), current=("Tally",)), [])

    def test_keep_and_match_forms_are_refused(self):
        for line in ("Keep the current layout.", "Preserve its navigation.", "Match the web look.",
                     "Mirror the existing screens.", "Use the same layout as the phone.",
                     "Stay consistent with the current app.", "It should look like the old app."):
            with self.subTest(line=line):
                self.assertTrue(codes(self.m.brief_faults(brief(job=JOB + "\n" + line))) & {"keep", "current"})

    def test_current_product_forms_are_refused(self):
        for line in ("Today's screens are too dense.", "The current view lists packages.",
                     "Study the live app.", "Draw it as it looks today, but better.",
                     "The native app has three tabs."):
            with self.subTest(line=line):
                self.assertIn("current", codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_screenshot_and_mockup_words_are_refused(self):
        for line in ("See the screenshot of the list.", "The old mockups were weak.", "A wireframe is attached."):
            with self.subTest(line=line):
                self.assertIn("screenshot", codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_paths_and_links_are_refused(self):
        for line in ("See captures/ui/packages.png.", "Open localhost:4190 first.",
                     "Read https://example.com/app.", "Look at docs/design/cards.html.",
                     "Read ~/notes/brief.txt."):
            with self.subTest(line=line):
                self.assertIn("path", codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_spec_and_tokens_are_refused(self):
        for line in ("Read SPEC.md before you draw.", "Follow the design spec.", "Use the design tokens.",
                     "The ink is --bn-ink.", "Follow the style guide."):
            with self.subTest(line=line):
                self.assertTrue(codes(self.m.brief_faults(brief(job=JOB + "\n" + line))) & {"spec", "path"})

    def test_d4_brief_with_a_palette_section_is_refused(self):
        found = codes(self.m.brief_faults(brief(palette=PALETTE)))
        self.assertTrue({"section-extra", "token-section"} <= found, found)

    def test_palette_section_is_refused_even_when_it_says_none(self):
        self.assertIn("token-section", codes(self.m.brief_faults(brief(palette="None."))))

    def test_colour_values_are_refused_in_a_free_section(self):
        for line in ("The accent is #3d5af1.", "Ink is #14161F80.", "The alert colour is #fa0.",
                     "Surface rgb(246, 247, 251).", "Text hsl(220 20% 10%).", "Accent oklch(0.6 0.2 260)."):
            for where in ("job", "device"):
                with self.subTest(line=line, where=where):
                    text = brief(**{where: (JOB if where == "job" else DEVICE) + "\n" + line})
                    self.assertIn("token-colour", codes(self.m.brief_faults(text)))

    def test_font_values_are_refused_in_a_free_section(self):
        for line in (FONTS, "font-family: Roboto", "Set it in SF Pro.", "Use a serif typeface.",
                     "Body is Helvetica Neue.", "Text in system-ui."):
            with self.subTest(line=line):
                self.assertIn("token-font", codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_spacing_values_are_refused_in_a_free_section(self):
        for line in (SPACING, "Gaps of 16px.", "Use --space-2 between rows.", "An 8-point grid.",
                     "Margin is 24 px.", "A 4 px step.", "Radius 12px."):
            with self.subTest(line=line):
                self.assertIn("token-spacing", codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_extra_colour_font_or_spacing_sections_are_refused(self):
        for name in ("Colours", "Colors", "Brand", "Fonts", "Typography", "Spacing", "Tokens", "Style"):
            with self.subTest(name=name):
                self.assertIn("token-section", codes(self.m.brief_faults(brief(extra="## %s\nAny." % name))))

    def test_plain_job_words_about_looks_pass(self):
        for line in ("He wears gloves, so touch targets are big.", "The mailbox is 30 inches deep.",
                     "Order #1234 arrived; envelope #12 is lost.", "Cards are 63 x 88 mm.",
                     "He reads at arm's length, in a dim room.", "A card costs 5 dollars.",
                     "The font on the envelope is hard to read.", "Inter-city mail takes 3 days."):
            with self.subTest(line=line):
                self.assertEqual(self.m.brief_faults(brief(job=JOB + "\n" + line)), [])

    def test_more_font_spacing_and_colour_leaks_are_refused(self):
        for key, line in (("token-font", "Headings in Satoshi, body in Lora."),
                          ("token-font", "The font is set in Fraunces."),
                          ("token-font", "Use Inter."), ("token-spacing", "Body text is 16px."),
                          ("token-spacing", "8px rounded corners."), ("token-spacing", "Leave 1.5rem between cards."),
                          ("token-spacing", "Padding of 12 pt."), ("token-colour", "Accent rgb (61,90,241)."),
                          ("token-colour", "Text colour #333."), ("token-colour", "Ink #333333."),
                          ("token-colour", "Surface hsl 220 90 60.")):
            with self.subTest(line=line):
                self.assertIn(key, codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_ids_names_and_plain_scales_in_a_job_pass(self):
        for line in ("Order #123456 arrived.", "Order #A123 is late.", "Lot #B12 is lost.", "Bin #C1D2 is full.",
                     "Invoice #12345678 is paid.", "He grades cards on a 10-point scale.",
                     "Inter Miami cards are rare.", "Gotham City cards sell fast.", "Menlo Park sellers ship late.",
                     "Rubik cards are rare.", "A serif logo is on the seal.", "The typeface on the card is old.",
                     "Profit margin is 5 percent.", "A step in the process takes 5 minutes."):
            with self.subTest(line=line):
                self.assertEqual(self.m.brief_faults(brief(job=JOB + "\n" + line)), [])

    def test_round_three_false_refusals_pass(self):
        for where, line in (("job", "A customer gets a text about order #1234."), ("job", "A paper slip #1234 comes in."),
                            ("job", "Each card has a title in English."), ("job", "The heading in German is odd."),
                            ("job", "A courier in San Francisco ships it."), ("job", "Montserrat sellers ship late."),
                            ("job", "Order #1A2B3C arrived."), ("device", "The lab (north wing) holds a phone.")):
            with self.subTest(line=line):
                text = brief(**{where: (JOB if where == "job" else DEVICE) + "\n" + line})
                self.assertEqual(self.m.brief_faults(text), [])

    def test_round_three_leaks_are_refused(self):
        for key, line in (("token-colour", "A solid #121212 background."), ("token-colour", "Mid #888888 for lines."),
                          ("token-colour", "A grid #333333 under it."), ("token-font", "The brand font is Inter."),
                          ("token-font", "The typeface is Lato."), ("token-font", "Font: Lato."),
                          ("token-font", "Use font Lato.")):
            with self.subTest(line=line):
                self.assertIn(key, codes(self.m.brief_faults(brief(job=JOB + "\n" + line))))

    def test_device_gap_inset_and_scale_sizes_pass(self):
        for line in ("8 px gap at the hinge.", "Hinge gap: 8 pt.", "Safe area: 47 pt top inset.",
                     "1114 x 705 pt, a grid of two screens.", "240 pt, one step down.",
                     "1114 x 705 pt in 2x scale."):
            with self.subTest(line=line):
                self.assertEqual(self.m.brief_faults(brief(device=DEVICE + "\n" + line)), [])

    def test_device_still_refuses_colour_and_font(self):
        for key, line in (("token-colour", "The shell is #3d5af1."), ("token-font", "Labels in Roboto.")):
            with self.subTest(line=line):
                self.assertIn(key, codes(self.m.brief_faults(brief(device=DEVICE + "\n" + line))))

    def test_text_on_the_kind_line_or_a_second_kind_line_is_refused(self):
        for header in ("Lane kind: blind, accent #3d5af1\nLane: packages-blind-1",
                       "Lane kind: blind\nLane kind: blind #3d5af1\nLane: packages-blind-1",
                       "Lane kind: blind\nLane kind: blind\nLane: packages-blind-1"):
            with self.subTest(header=header):
                self.assertIn("outside", codes(self.m.brief_faults(brief(header=header))))

    def test_long_digit_run_is_fast(self):
        import time
        start = time.time()
        self.m.brief_faults(brief(job=JOB + "\n" + "1" * 20000))
        self.assertLess(time.time() - start, 2)

    def test_device_written_sizes_pass(self):
        line = "iPhone Duo, 1114 x 705 pt open, 540 x 720 px per screen."
        self.assertEqual(self.m.brief_faults(brief(device=DEVICE + "\n" + line)), [])

    def test_house_rules_text_names_no_palette_and_closes_the_token_files(self):
        self.assertNotIn("Palette", fixed("House rules"))
        self.assertIn("repo-colours.json", fixed("House rules"))

    def test_changed_fixed_section_is_refused(self):
        text = brief().replace(fixed("Deliver"), fixed("Deliver") + " Keep it close to today.")
        self.assertIn("fixed-changed", codes(self.m.brief_faults(text)))

    def test_extra_section_is_refused(self):
        self.assertIn("section-extra", codes(self.m.brief_faults(brief(extra="## Current screens\nThree tabs."))))

    def test_missing_section_is_refused(self):
        text = brief().replace("## Device\n" + DEVICE + "\n", "")
        self.assertIn("section-missing", codes(self.m.brief_faults(text)))

    def test_empty_free_section_is_refused(self):
        self.assertIn("section-empty", codes(self.m.brief_faults(brief(device=""))))

    def test_text_outside_the_template_is_refused(self):
        header = "Lane kind: blind\nLane: packages-blind-1\nSee the app before you start."
        self.assertIn("outside", codes(self.m.brief_faults(brief(header=header))))

    def test_missing_lane_line_is_refused(self):
        self.assertIn("lane", codes(self.m.brief_faults(brief(header="Lane kind: blind"))))

    def test_sub_heading_inside_job_passes(self):
        self.assertEqual(self.m.brief_faults(brief(job=JOB + "\n### On mail day\nHe sorts by seller.")), [])

    def test_plain_job_words_pass(self):
        for line in ("Keep the screen on while sorting.", "Each card has a spec sheet.",
                     "He signs in with a login token.", "Orders hold qty <5 and >2.",
                     "He sorts by date and/or app/seller.", "Keep the design simple for her.",
                     "Keep the structure of boxes tidy.", "Copy the app seller name.",
                     "Match the look of a label to an order."):
            with self.subTest(line=line):
                self.assertEqual(self.m.brief_faults(brief(job=JOB + "\n" + line)), [])

    def test_lane_name_with_capitals_and_underscore_passes(self):
        self.assertEqual(self.m.brief_faults(brief(header="Lane kind: blind\nLane: Pack_view-blind-1")), [])

    def test_wrong_kind_line_is_refused(self):
        self.assertIn("kind", codes(self.m.brief_faults(brief(header="Lane kind: informed\nLane: packages-blind-1"))))


class RunFaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_duo_run_with_no_blind_lane_is_refused(self):
        # The incident run: one brief, no blind lane.
        found = codes(self.m.run_faults(["Lane kind: informed\nBlind lanes: 0\n\n" + DUO_BRIEF]))
        self.assertIn("no-blind-lane", found)

    def test_run_with_a_brief_with_no_kind_is_refused(self):
        self.assertIn("kind", codes(self.m.run_faults([brief(), DUO_BRIEF])))

    def test_run_with_a_clean_blind_lane_passes(self):
        informed = "Lane kind: informed\nBlind lanes: 1\n\nDraw the packages screen from the spec."
        self.assertEqual(self.m.run_faults([brief(), informed]), [])

    def test_run_with_only_informed_lanes_passes_on_owner_words(self):
        informed = "Lane kind: informed\nBlind lanes: none\n\nDraw it."
        self.assertEqual(self.m.run_faults([informed], owner_none="only informed lanes this time"), [])

    def test_run_with_a_bad_blind_lane_is_refused(self):
        bad = brief(job=JOB + "\nKeep the current layout.")
        self.assertIn("keep", codes(self.m.run_faults([bad])))


def run_cli(*args, env=None):
    return subprocess.run([sys.executable, MODULE] + list(args), capture_output=True, text=True,
                          env=env, timeout=60)


class Cli(unittest.TestCase):
    def test_clean_folder_exits_0(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "packages-blind-1.md"), "w", encoding="utf-8") as h:
                h.write(brief())
            done = run_cli("--run", folder)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_duo_folder_exits_1_and_names_the_fault(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "duo-informed-1.md"), "w", encoding="utf-8") as h:
                h.write("Lane kind: informed\nBlind lanes: 0\n\n" + DUO_BRIEF)
            done = run_cli("--run", folder)
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("no-blind-lane", done.stdout)

    def test_current_names_reach_the_check(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "packages-blind-1.md"), "w", encoding="utf-8") as h:
                h.write(brief(job=JOB + "\nPut Tally on the left page."))
            done = run_cli("--run", folder, "--current", "Tally")
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("named-view", done.stdout)

    def test_owner_none_reaches_the_check(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "packages-informed-1.md"), "w", encoding="utf-8") as h:
                h.write("Lane kind: informed\nBlind lanes: none\n\nDraw it.")
            done = run_cli("--run", folder, "--owner-asked-none", "informed only")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_missing_folder_exits_2(self):
        done = run_cli("--run", os.path.join(tempfile.gettempdir(), "no-such-blind-brief-folder"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)

    def test_empty_folder_exits_1(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(run_cli("--run", folder).returncode, 1)


class Devices(unittest.TestCase):
    """The designer agent, the brief template and the hook read one resolved device list (step c113)."""
    @classmethod
    def setUpClass(cls):
        cls.m = load()
        spec = importlib.util.spec_from_file_location("layout_for_brief_test",
                                                      os.path.join(HERE, "..", "lint", "layout.py"))
        cls.layout = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.layout)

    def repo(self, **keys):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, ".claude"))
        with open(os.path.join(folder.name, ".claude", "layout-extras.json"), "w", encoding="utf-8") as h:
            json.dump(dict({"kinds": {}}, **keys), h)
        return folder.name

    def test_the_hook_reads_the_same_list_as_the_layout(self):
        root = self.repo(kind="ios")
        self.assertEqual(self.m.device_names(root), [d["name"] for d in self.layout.devices(root)])

    def test_a_repo_with_no_kind_has_no_device_to_check(self):
        self.assertIsNone(self.m.device_names(self.repo()))
        self.assertEqual(self.m.brief_faults(brief(), devices=None), [])

    def test_a_brief_must_draw_the_first_device_first(self):
        first = self.m.device_names(self.repo(kind="ios"))[0]
        self.assertIn("device-first", codes(self.m.brief_faults(brief(device="A phone."), devices=[first])))
        self.assertEqual(self.m.brief_faults(brief(device=DEVICE + " " + first + "."), devices=[first]), [])

    def test_the_hook_judges_a_spawn_by_its_cwd_repo(self):
        root = self.repo(kind="ios")
        out = Hook("test_clean_blind_designer_spawn_passes")
        out.setUp()
        self.addCleanup(out.tearDown)
        done = out.hook({"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "s1", "cwd": root,
                         "tool_input": {"subagent_type": "designer", "prompt": brief(device="A phone."),
                                        "description": "lane"}})
        out.assertRefused(done)

    def test_the_cli_takes_the_repo_root(self):
        root = self.repo(kind="ios")
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "packages-blind-1.md"), "w", encoding="utf-8") as h:
                h.write(brief(device="A phone."))
            done = run_cli("--run", folder, "--root", root)
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("device-first", done.stdout)

    def test_paraphrases_of_the_first_device_pass(self):
        first = "iPhone Duo, folded"
        for text in ("An iPhone Duo (folded), held like a book.", "Duo folded on a desk.",
                     "the IPHONE   DUO -- FOLDED pose", "Folded iPhone Duo."):
            with self.subTest(text=text):
                self.assertEqual(self.m.brief_faults(brief(device=text), devices=[first]), [])

    def test_a_different_device_first_is_still_refused(self):
        first = "iPhone Duo, folded"
        for text in ("iPhone Duo, unfolded, flat on a table.", "A regular iPhone.", "Duo only."):
            with self.subTest(text=text):
                self.assertIn("device-first", codes(self.m.brief_faults(brief(device=text), devices=[first])))

    def test_designer_and_template_point_at_the_one_command_and_name_no_device(self):
        names = [d["name"].lower() for d in self.layout.layout()["devices"].values()]
        for rel in ("agents/designer.md", "skills/design-explore/blind-brief.md", "skills/design-explore/SKILL.md"):
            with self.subTest(file=rel):
                with open(os.path.join(HERE, "..", rel), encoding="utf-8") as h:
                    text = h.read()
                self.assertIn("layout.py devices", text)
                for name in names:
                    self.assertNotIn(name, text.lower())


class DesignerSteps(unittest.TestCase):
    """The designer loads a design skill before it draws and critiques its own mockup before it reports.

    A plain text check of the body of agents/designer.md. Each step is bound to a line anchor, so a
    step moved after the work it must precede fails. The sentence that orders a step must not be
    negated ("never load", "skip"), and a word in an unrelated sentence orders nothing. A negated
    sentence elsewhere in the same paragraph is fine.
    """
    DRAW = "For each screen the brief names"
    REPORT = "Report once"
    NEGATED = re.compile(r"\b(?:never|not|no|skip|skips|without)\b|n't", re.I)
    # The blind-lane exception is a skip by nature, so a sentence that names it never orders the run.
    SETUP = re.compile(r"\b(?:Setup|Launcher)\b")

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, "..", "agents", "designer.md"), encoding="utf-8") as h:
            lines = h.read().splitlines()
        fence = [i for i, line in enumerate(lines) if line == "---"]
        cls.lines = lines[fence[1] + 1:] if len(fence) > 1 and fence[0] == 0 else lines

    def at(self, anchor):
        hits = [i for i, line in enumerate(self.lines) if line.startswith(anchor)]
        self.assertTrue(hits, "agents/designer.md has no line starting %r" % anchor)
        return hits[0]

    def steps(self, stop, start=None):
        """Each paragraph or list item from the line starting `start` up to the line starting `stop`, as sentences."""
        lo = 0 if start is None else self.at(start)
        units = re.split(r"\n\s*\n|\n(?=\s*[-*] )", "\n".join(self.lines[lo:self.at(stop)]))
        return [re.split(r"(?<=[.!?])\s+", " ".join(u.split())) for u in units]

    def orders_critique(self, sentence):
        return (all(re.search(w, sentence, re.I) for w in (r"\brun\b", r"\bimpeccable\b", r"\bcritique\b"))
                and not self.NEGATED.search(sentence) and not self.SETUP.search(sentence))

    def skips_setup_in_a_blind_lane(self, sentence):
        skip = re.search(r"\bskip\b", sentence, re.I)
        return bool(skip and not self.NEGATED.search(sentence[:skip.start()]) and re.search(r"\bblind\b", sentence, re.I)
                    and "Setup" in sentence and "Launcher unavailable" in sentence)

    def test_loads_frontend_design_by_name_before_it_draws(self):
        found = [s for step in self.steps(self.DRAW) for s in step
                 if re.search(r"\bload\w*", s, re.I) and "frontend-design" in s and not self.NEGATED.search(s)]
        self.assertTrue(found, "no sentence loads `frontend-design` before the line starting %r" % self.DRAW)

    def test_critiques_its_own_mockup_with_impeccable_before_it_reports(self):
        self.assertTrue(any(re.search(r"\bown mockup\b", " ".join(step), re.I)
                            and any(self.orders_critique(s) for s in step) for step in self.steps(self.REPORT)),
                        "no step has a sentence that runs `impeccable` `critique` on its own mockup before the line "
                        "starting %r" % self.REPORT)

    def test_a_blind_lane_critique_skips_impeccable_setup_and_its_launcher_fallback(self):
        # Setup and the Launcher fallback read PRODUCT.md and DESIGN.md, which a blind lane may not read.
        self.assertTrue(any(self.skips_setup_in_a_blind_lane(s)
                            for step in self.steps(self.REPORT, start=self.DRAW) for s in step),
                        "no sentence between the lines starting %r and %r skips impeccable's Setup and its "
                        "Launcher fallback in a blind lane" % (self.DRAW, self.REPORT))


class Hook(unittest.TestCase):
    def setUp(self):
        self.config = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=self.config.name)

    def tearDown(self):
        self.config.cleanup()

    def hook(self, payload):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        done = subprocess.run([sys.executable, MODULE], input=stdin, capture_output=True, text=True,
                              env=self.env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def spawn(self, prompt, role="designer", tool="Agent"):
        return self.hook({"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "s1",
                          "tool_input": {"subagent_type": role, "prompt": prompt, "description": "lane"}})

    def assertRefused(self, out):
        self.assertTrue(out, "want a refusal, got no output")
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertTrue(decision["permissionDecisionReason"].startswith("blind-brief: "), decision)

    def test_clean_blind_designer_spawn_passes(self):
        self.assertEqual(self.spawn(brief()), "")

    def test_duo_blind_designer_spawn_is_refused(self):
        self.assertRefused(self.spawn("Lane kind: blind\nLane: duo-blind-1\n\n" + DUO_BRIEF))

    def test_blind_spawn_with_keep_rule_is_refused_on_task_too(self):
        self.assertRefused(self.spawn(brief(job=JOB + "\nKeep the current layout."), tool="Task"))

    def test_plugin_prefixed_designer_is_judged(self):
        self.assertRefused(self.spawn(brief(job=JOB + "\nKeep the current layout."), role="kit:designer"))

    def test_informed_spawn_with_no_blind_lanes_line_is_refused(self):
        self.assertRefused(self.spawn("Lane kind: informed\n\n" + DUO_BRIEF))

    def test_informed_spawn_with_zero_blind_lanes_is_refused(self):
        self.assertRefused(self.spawn("Lane kind: directed, denser\nBlind lanes: 0\n\nDraw it."))

    def test_informed_spawn_with_blind_lanes_passes(self):
        self.assertEqual(self.spawn("Lane kind: informed\nBlind lanes: 2\n\n" + DUO_BRIEF), "")

    def test_informed_spawn_with_owner_none_passes(self):
        self.assertEqual(self.spawn('Lane kind: informed\nBlind lanes: none, owner: "informed only"\n\nDraw it.'), "")

    def test_owner_none_with_no_words_is_refused(self):
        self.assertRefused(self.spawn("Lane kind: informed\nBlind lanes: none\n\nDraw it."))

    def test_blind_kind_after_a_preamble_is_judged(self):
        self.assertRefused(self.spawn("You are the designer.\nLane kind: blind\nLane: duo-blind-1\n\n" + DUO_BRIEF))

    def test_informed_kind_after_a_preamble_is_judged(self):
        self.assertRefused(self.spawn("You are the designer.\nLane kind: informed\n\nDraw it."))

    def test_designer_spawn_with_no_kind_passes(self):
        # A small change to one screen skips design-explore and names no kind.
        self.assertEqual(self.spawn(DUO_BRIEF), "")

    def test_other_role_passes(self):
        self.assertEqual(self.spawn("Lane kind: blind\n" + DUO_BRIEF, role="builder"), "")

    def test_other_tool_passes(self):
        self.assertEqual(self.hook({"tool_name": "Bash", "tool_input": {"command": "true"}}), "")

    def test_junk_input_passes(self):
        self.assertEqual(self.hook("not json"), "")
        self.assertEqual(self.hook("[]"), "")

    def test_refusal_is_logged(self):
        self.spawn(brief(job=JOB + "\nKeep the current layout."))
        with open(os.path.join(self.config.name, "guard.log"), encoding="utf-8") as handle:
            self.assertIn("blind-brief", handle.read())


IOS_DEVICE = (
    "Two poses of the iPhone Duo, drawn in this order. First, iPhone Duo, folded: a tent on a desk, one "
    "screen up. Then iPhone Duo, unfolded: open as a book, both screens side by side. Touch only. Follow "
    "skill ios-apps and the Apple Human Interface Guidelines. Use native controls, lists and sheets. Respect "
    "the safe-area insets. Use the system font and Dynamic Type for all text. Use 44 pt touch targets. Each "
    "pose gets its own layout, never a stretched phone.")
IOS_DEVICE_NO_SKILL = IOS_DEVICE.replace("Follow skill ios-apps and the Apple", "Follow the Apple")


def app_repo(kind):
    """A repo folder under the run folder whose extras file names its app kind, as lint/layout.py reads it."""
    root = tempfile.mkdtemp(dir=RUN_FOLDER)
    os.makedirs(os.path.join(root, ".claude"))
    with open(os.path.join(root, ".claude", "layout-extras.json"), "w", encoding="utf-8") as handle:
        json.dump({"kinds": {}, "kind": kind}, handle)
    return root


def fault_codes(stdout):
    """The fault codes the CLI printed: the first word of each line, without its summary line."""
    return {line.split(":", 1)[0] for line in stdout.splitlines() if line and not line.startswith("blind_brief:")}


def check_run(texts, root=None):
    """The CLI's verdict on one explore run of briefs, as (exit code, fault codes, stdout)."""
    folder = tempfile.mkdtemp(dir=RUN_FOLDER)
    for index, text in enumerate(texts):
        with open(os.path.join(folder, "lane-%d.md" % (index + 1)), "w", encoding="utf-8") as handle:
            handle.write(text)
    done = run_cli("--run", folder, *(["--root", root] if root else []))
    return done.returncode, fault_codes(done.stdout), done.stdout


def spawn_in(root, prompt, role="designer", tool="Agent"):
    """The hook's stdout for one spawn whose cwd is `root`. Its config folder is under the run folder."""
    config = tempfile.mkdtemp(dir=RUN_FOLDER)
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "s1", "cwd": root,
               "tool_input": {"subagent_type": role, "prompt": prompt, "description": "lane"}}
    done = subprocess.run([sys.executable, MODULE], input=json.dumps(payload), capture_output=True, text=True,
                          env=dict(os.environ, CLAUDE_CONFIG_DIR=config), timeout=60)
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return done.stdout.strip()


def reason_of(out):
    return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]


class IosApps(unittest.TestCase):
    """An iOS app repo (app kind `ios`, roadmap step c192) draws the Duo fold first and names skill ios-apps.
    The CLI reads the repo from --root, and the hook from the spawn's cwd."""
    @classmethod
    def setUpClass(cls):
        cls.ios = app_repo("ios")
        cls.web = app_repo("web")

    def test_device_naming_only_unfolded_is_refused_first(self):
        code, found, out = check_run([brief(device="iPhone Duo, unfolded.")], self.ios)
        self.assertEqual(code, 1, out)
        self.assertIn("device-first", found, out)

    def test_folded_named_without_unfolded_gets_duo_unfolded(self):
        device = "A folding phone. Draw the iPhone Duo, folded: a tent on a desk. Touch only."
        code, found, out = check_run([brief(device=device)], self.ios)
        self.assertIn("duo-unfolded", found, out)

    def test_unfolded_named_before_folded_gets_duo_order(self):
        device = ("A folding phone. Draw the iPhone Duo, unfolded, open as a book; then the iPhone Duo, folded, "
                  "a tent on a desk. Touch only.")
        code, found, out = check_run([brief(device=device)], self.ios)
        self.assertIn("duo-order", found, out)

    def test_unfolded_named_after_folded_gets_no_duo_order(self):
        device = "iPhone Duo, unfolded, drawn after the folded pose."
        code, found, out = check_run([brief(device=device)], self.ios)
        self.assertNotIn("duo-order", found, out)

    def test_blind_brief_that_never_names_ios_apps_gets_ios_skill(self):
        code, found, out = check_run([brief(device=IOS_DEVICE_NO_SKILL)], self.ios)
        self.assertIn("ios-skill", found, out)

    def test_blind_spawn_that_never_names_ios_apps_is_refused_with_ios_skill(self):
        out = spawn_in(self.ios, brief(device=IOS_DEVICE_NO_SKILL))
        self.assertTrue(out, "want a refusal, got no output")
        self.assertIn("ios-skill", reason_of(out))

    def test_informed_spawn_without_ios_apps_gets_ios_skill(self):
        prompt = "Lane kind: informed\nBlind lanes: 2\n\nDraw the packages screens: the iPhone Duo, folded, then unfolded."
        out = spawn_in(self.ios, prompt)
        self.assertTrue(out, "want a refusal, got no output")
        self.assertIn("ios-skill", reason_of(out))

    def test_informed_spawn_still_needs_its_blind_lanes_line(self):
        prompt = "Lane kind: informed\n\nFollow skill ios-apps. Draw the iPhone Duo, folded, then unfolded."
        self.assertIn("Blind lanes", reason_of(spawn_in(self.ios, prompt)))

    def test_informed_spawn_with_blind_lanes_and_ios_apps_passes(self):
        prompt = "Lane kind: informed\nBlind lanes: 2\n\nFollow skill ios-apps. Draw the iPhone Duo, folded, then unfolded."
        self.assertEqual(spawn_in(self.ios, prompt), "")

    def test_valid_ios_blind_brief_has_zero_faults(self):
        code, found, out = check_run([brief(device=IOS_DEVICE)], self.ios)
        self.assertEqual((code, found), (0, set()), out)

    def test_web_blind_brief_is_unchanged_and_green(self):
        device = "Phone width first, then desktop width. Touch on the phone, a mouse on the desktop."
        code, found, out = check_run([brief(device=device)], self.web)
        self.assertEqual((code, found), (0, set()), out)

    def test_blind_brief_with_no_kind_line_in_an_ios_repo_passes(self):
        self.assertEqual(spawn_in(self.ios, "Draw the packages screens for the iPhone Duo. Touch only."), "")

    def device_codes(self, device):
        """(fault codes, stdout) of one blind brief whose Device section is `device`, in the ios repo. The Job
        names skill ios-apps, so the Device section is the only part of the brief that can fault."""
        code, found, out = check_run([brief(job=JOB + "\nFollow skill ios-apps.", device=device)], self.ios)
        return found, out

    def test_short_form_unfolded_then_folded_gets_duo_order(self):
        found, out = self.device_codes("Draw iPhone Duo unfolded, then folded.")
        self.assertEqual(found, {"duo-order"}, out)

    def test_short_form_unfolded_first_then_the_folded_pose_gets_duo_order(self):
        found, out = self.device_codes("Duo unfolded first, then the Duo in folded pose.")
        self.assertEqual(found, {"duo-order"}, out)

    def test_short_form_unfolded_pose_and_folded_pose_gets_duo_order(self):
        found, out = self.device_codes("Duo unfolded pose and folded pose.")
        self.assertEqual(found, {"duo-order"}, out)

    def test_short_form_folded_first_then_unfolded_gets_no_duo_order(self):
        found, out = self.device_codes("Folded Duo first, then unfolded Duo.")
        self.assertEqual(found, set(), out)

    def test_short_form_folded_then_unfolded_in_parentheses_gets_no_duo_order(self):
        found, out = self.device_codes("Duo (folded) on one hand, Duo (unfolded) on two hands.")
        self.assertEqual(found, set(), out)

    def test_full_form_folded_then_unfolded_gets_no_duo_order(self):
        found, out = self.device_codes("iPhone Duo, folded, then iPhone Duo, unfolded.")
        self.assertEqual(found, set(), out)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main(verbosity=1)
