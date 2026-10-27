#!/usr/bin/env python3
"""Cases for hooks/blind_brief.py, the blind design brief check. Standard library only.

Run it from the repository root:

    python3 hooks/test_blind_brief.py

Contract (the module's own docstring):
- `brief_faults(text, current=())` lists the faults of one blind brief. A clean brief has none.
  A brief must follow skills/design-explore/blind-brief.md: a `Lane kind: blind` line, a `Lane:` line,
  the free sections Job, Device and Palette, and the fixed sections House rules and Deliver word for
  word. A free section may not name the current product, a screenshot or mockup, a path or link, the
  spec or tokens, or a keep or match rule. `current` names views of today's product, refused as words.
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
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("BLIND_BRIEF_UNDER_TEST") or os.path.join(HERE, "blind_brief.py")
TEMPLATE = os.path.join(HERE, "..", "skills", "design-explore", "blind-brief.md")


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

PALETTE = "Parchment #F4ECD8, ink #2B2118, gold #B08D57, green #2F6B3F."


def fixed(name):
    """The fixed section `name` of the template, its body as written there."""
    with open(TEMPLATE, encoding="utf-8") as handle:
        text = handle.read()
    head = "## " + name + "\n"
    body = text.split(head, 1)[1]
    return body.split("\n## ", 1)[0].strip()


def brief(job=JOB, device=DEVICE, palette=PALETTE, header="Lane kind: blind\nLane: packages-blind-1",
          extra=""):
    return "\n".join([
        header, "",
        "## Job", job, "",
        "## Device", device, "",
        "## Palette", palette, "",
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
        for name, body in (("Job", JOB), ("Device", DEVICE), ("Palette", PALETTE)):
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

    def test_palette_section_is_scanned_too(self):
        self.assertIn("spec", codes(self.m.brief_faults(brief(palette="Take the colours from the tokens file."))))

    def test_changed_fixed_section_is_refused(self):
        text = brief().replace(fixed("Deliver"), fixed("Deliver") + " Keep it close to today.")
        self.assertIn("fixed-changed", codes(self.m.brief_faults(text)))

    def test_extra_section_is_refused(self):
        self.assertIn("section-extra", codes(self.m.brief_faults(brief(extra="## Current screens\nThree tabs."))))

    def test_missing_section_is_refused(self):
        text = brief().replace("## Palette\n" + PALETTE + "\n", "")
        self.assertIn("section-missing", codes(self.m.brief_faults(text)))

    def test_empty_free_section_is_refused(self):
        self.assertIn("section-empty", codes(self.m.brief_faults(brief(device=""))))

    def test_text_outside_the_template_is_refused(self):
        header = "Lane kind: blind\nLane: packages-blind-1\nSee the app before you start."
        self.assertIn("outside", codes(self.m.brief_faults(brief(header=header))))

    def test_missing_lane_line_is_refused(self):
        self.assertIn("lane", codes(self.m.brief_faults(brief(header="Lane kind: blind"))))

    def test_hex_first_palette_lines_pass(self):
        self.assertEqual(self.m.brief_faults(brief(palette="#F4ECD8 parchment\n#2B2118 ink")), [])

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
