#!/usr/bin/env python3
"""Cases for the lane start in one pass (branch lane-start-one-pass): bin/lane-start (Change 2), the constants that the
helper and the guard share (Change 2), and the handoff and project-ops templates that name the helper (Change 3).
Stdlib and unittest.

    python3 lint/test_lane_start.py

The guard's cases, the combined refusal and the archive read messages, are in tests/guard/s43500-lane-start-pass.py, which
hooks/test_guard.py runs. The helper cases run bin/lane-start as a child process, from a fixture checkout whose origin is
set here, so no case reads the real repo. Each case writes only in this run's folder (test-temp-standard, lint/_test_temp.py).
Source checks read the code with the ast module, so a comment or a docstring never counts as a literal.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()
HELPER = os.path.join(REPO, "bin", "lane-start")
WRAPPER = os.path.join(REPO, "bin", "lane-start.cmd")
GUARD_SOURCE = os.path.join(REPO, "hooks", "guard.py")
GUARD_MERGE_SOURCE = os.path.join(REPO, "hooks", "guard_merge.py")
SHARED_NAMES = os.path.join(REPO, "hooks", "shared_names.py")
HANDOFF_PROMPT = os.path.join(REPO, "hooks", "precompact_handoff_prompt.md")
TEMPLATES = os.path.join(REPO, "skills", "project-ops", "templates")

OWNER_REPO = "shivinate7/claude-settings"
ORIGIN_URL = "https://github.com/" + OWNER_REPO
GRANT = "Grant: B is good, 13:19 CST Nov 10"
SLUG = "fan-settings"
TOPIC = "thermostat"
LANE_BRIEF = "Lane brief: %s. Topic: %s." % (SLUG, TOPIC)
FULL_SLUG = "abcdefghijklmnopqrstuvwxyz012345"  # 32 characters, the longest slug the Git rule allows
# The literal copies a helper or a check must not hold: the values of shared_names' constants, read by prefix or whole.
LANE_EFFORT_VALUE = "medium"
LANE_MODEL_VALUE = "sonnet"
TAG_PREFIXES = ("cs-build:", "cs-repo:", "cs-topic:", "cs-step:")
LANE_BRIEF_VALUE = "Lane brief:"
TITLE_FORM = re.compile(r"Lane <(?:branch )?slug>:")
LIST_TOOL = "mcp__claude-code-remote__list_sessions"
CARRIER_ID = "session_LANECARRIER01"  # a live lane that carries the step, in the transcript's whole list read


def write_list_transcript(path, rows):
    """A transcript of one whole list_sessions read that shows `rows`, one JSON line per message, as the session writes it.
    The guard reads it for a live lane that carries the start's step (lane-step-dup)."""
    body = json.dumps({"ccr": {"data": rows, "has_more": False}})
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "list1", "name": LIST_TOOL, "input": {}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "list1", "content": [{"type": "text", "text": body}]}]}},
    ]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(line) for line in lines) + "\n")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def tree_listing(folder):
    """Every path under `folder`, relative, so a run that writes a file shows as a change."""
    listed = set()
    for here, dirs, files in os.walk(folder):
        for name in dirs + files:
            listed.add(os.path.relpath(os.path.join(here, name), folder))
    return listed


def module_assigns(path):
    """(name, value node) for each module-level assignment of a Python file, read with ast. A tuple target pairs each
    name with its value's element. A file that does not parse raises, so a broken source fails the case."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    pairs = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                pairs.append((target.id, node.value))
            elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple) \
                    and len(target.elts) == len(node.value.elts):
                pairs.extend((elt.id, value) for elt, value in zip(target.elts, node.value.elts)
                             if isinstance(elt, ast.Name))
    return pairs


def str_value(node):
    """The text of a string literal node, or None for any other node."""
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def imported_from_shared_names(path):
    """The names a module imports from shared_names, read with ast."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "shared_names":
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def units_of(text):
    """The units of a markdown template: a bullet with its continuation lines, or a line that is not in a bullet, each
    joined to one line. A blank line ends a unit."""
    units, current = [], []
    for line in text.splitlines():
        if not line.strip():
            if current:
                units.append(" ".join(current))
            current = []
        elif line.startswith("- ") and current:
            units.append(" ".join(current))
            current = [line.strip()]
        else:
            current.append(line.strip())
    if current:
        units.append(" ".join(current))
    return units


def recipe_markers(unit):
    """The markers of a lane-start recipe in one unit: the lane title form, or `source_url` with `effort` (the field list of
    a start), or `create_session` with `cs-repo:` (a tag list beside the tool). Each is in a recipe and in no pointer."""
    found = []
    if TITLE_FORM.search(unit):
        found.append("the lane title form")
    if "source_url" in unit and "effort" in unit:
        found.append("the source_url and effort field list")
    if "create_session" in unit and "cs-repo:" in unit:
        found.append("cs-repo: beside create_session")
    return found


class RecipeDetector(unittest.TestCase):
    """The detector is a check of its own: it must flag a recipe and pass a pointer, or the template cases prove nothing."""

    def test_the_detector_flags_the_title_form_and_passes_a_pointer(self):
        recipe = "It starts each lane with `model` and `source_url` (the repo), effort `medium` and `title` `Lane <branch slug>: <task>`."
        pointer = "It starts each lane with `bin/lane-start`, which prints the start's fields."
        self.assertTrue(recipe_markers(recipe), "the detector passes a lane start that names its title form and effort")
        self.assertEqual(recipe_markers(pointer), [], "the detector flags a pointer to the helper as a recipe")

    def test_units_split_a_bullet_from_the_next_and_keep_its_continuation_lines(self):
        text = "- **One.** first\n  continued here\n- **Two.** second\n\nplain paragraph\n"
        self.assertEqual(units_of(text), ["- **One.** first continued here", "- **Two.** second", "plain paragraph"])


class LaneStartHelper(unittest.TestCase):
    """bin/lane-start: the one JSON object of a create_session's fields, or a refusal on stderr with exit 2."""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="lane_start_cases_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.work, True)

    def brief(self, text, name="brief.md"):
        path = os.path.join(self.work, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def checkout(self, origin=ORIGIN_URL, name="checkout"):
        """A git checkout of the fixture folder whose origin is `origin`. Only this run's folder holds it."""
        where = os.path.join(self.work, name)
        os.makedirs(where)
        for args in (["init", "-q"], ["remote", "add", "origin", origin]):
            done = subprocess.run(["git"] + args, cwd=where, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, "fixture git %s failed: %s" % (args[0], done.stderr))
        return where

    def run_helper(self, *args, cwd=None):
        self.assertTrue(os.path.isfile(HELPER), "bin/lane-start is missing, so no lane start can be printed")
        return subprocess.run([sys.executable, HELPER] + list(args), cwd=cwd or self.work,
                              capture_output=True, text=True, timeout=60)

    def start(self, *extra, brief_text="Do the task.\n", grant=GRANT, slug=SLUG, topic=TOPIC):
        """A successful start, with its JSON decoded. Fails the case, with the helper's stderr, when the helper refuses."""
        run = self.run_helper(slug, topic, grant, self.brief(brief_text), *extra)
        self.assertEqual(run.returncode, 0, "bin/lane-start exits %d, want 0: %s" % (run.returncode, run.stderr))
        try:
            fields = json.loads(run.stdout)
        except ValueError as err:
            self.fail("bin/lane-start printed no JSON object (%s): %r" % (err, run.stdout[:120]))
        self.assertIsInstance(fields, dict, "bin/lane-start's JSON is not one object")
        return fields

    def assert_refused(self, run, rule=None):
        """A refusal: exit 2, no JSON on stdout, and the stderr that names the rule (when given)."""
        self.assertEqual(run.returncode, 2, "bin/lane-start exits %d, want 2: %s" % (run.returncode, run.stderr))
        self.assertEqual(run.stdout, "", "a refused lane start printed on stdout: %r" % run.stdout[:120])
        if rule:
            self.assertIn(rule, run.stderr, "the refusal names no %s: %s" % (rule, run.stderr))

    def test_a_start_prints_one_json_object_with_the_create_session_fields(self):
        fields = self.start("--repo", OWNER_REPO)
        self.assertEqual(fields["title"], "Lane %s: %s" % (SLUG, TOPIC))
        self.assertCountEqual(fields["tags"], ["cs-build:lane", "cs-topic:" + TOPIC, "cs-step:" + SLUG, "cs-repo:" + OWNER_REPO])
        self.assertEqual(fields["model"], LANE_MODEL_VALUE)
        self.assertEqual(fields["effort"], LANE_EFFORT_VALUE)
        self.assertEqual(fields["source_url"], ORIGIN_URL)

    def test_the_prompt_is_the_grant_then_the_lane_brief_line_then_the_brief(self):
        fields = self.start("--repo", OWNER_REPO, brief_text="Do the task.\nTouch only lib/fan.py.\n")
        lines = fields["prompt"].splitlines()
        self.assertEqual(lines[0], GRANT)
        self.assertEqual(lines[1], LANE_BRIEF)
        self.assertIn("Do the task.", lines[2:])
        self.assertIn("Touch only lib/fan.py.", lines[2:])

    def test_a_brief_that_opens_with_the_grant_and_the_lane_brief_line_keeps_each_once(self):
        fields = self.start("--repo", OWNER_REPO, brief_text=GRANT + "\n" + LANE_BRIEF + "\nDo the task.\n")
        prompt = fields["prompt"]
        self.assertEqual(prompt.count("Grant:"), 1, "the prompt holds the Grant line %d times" % prompt.count("Grant:"))
        self.assertEqual(prompt.count("Lane brief:"), 1, "the prompt holds the Lane brief line %d times" % prompt.count("Lane brief:"))
        self.assertIn("Do the task.", prompt)

    def test_an_empty_brief_file_still_prints_the_grant_and_the_lane_brief_line(self):
        fields = self.start("--repo", OWNER_REPO, brief_text="")
        lines = fields["prompt"].splitlines()
        self.assertEqual(lines[:2], [GRANT, LANE_BRIEF])

    def test_a_full_size_32_character_slug_prints_its_title(self):
        self.assertEqual(len(FULL_SLUG), 32, "fixture setup failed: FULL_SLUG is %d characters" % len(FULL_SLUG))
        fields = self.start("--repo", OWNER_REPO, slug=FULL_SLUG)
        self.assertEqual(fields["title"], "Lane %s: %s" % (FULL_SLUG, TOPIC))
        self.assertIn("cs-step:" + FULL_SLUG, fields["tags"])

    def test_the_repo_defaults_to_the_origin_of_the_checkout(self):
        where = self.checkout()
        run = self.run_helper(SLUG, TOPIC, GRANT, self.brief("Do the task.\n"), cwd=where)
        self.assertEqual(run.returncode, 0, "bin/lane-start with no --repo exits %d: %s" % (run.returncode, run.stderr))
        fields = json.loads(run.stdout)
        self.assertIn("cs-repo:" + OWNER_REPO, fields["tags"])
        self.assertEqual(fields["source_url"], ORIGIN_URL)

    def test_the_repo_flag_wins_over_the_origin(self):
        where = self.checkout()
        run = self.run_helper(SLUG, TOPIC, GRANT, self.brief("Do the task.\n"), "--repo", "shivinate7/other-repo", cwd=where)
        self.assertEqual(run.returncode, 0, "bin/lane-start with --repo exits %d: %s" % (run.returncode, run.stderr))
        fields = json.loads(run.stdout)
        self.assertIn("cs-repo:shivinate7/other-repo", fields["tags"])
        self.assertEqual(fields["source_url"], "https://github.com/shivinate7/other-repo")

    def test_the_helper_writes_no_file(self):
        where = self.checkout()
        brief = self.brief("Do the task.\n")
        before = (tree_listing(self.work), tree_listing(where))
        run = self.run_helper(SLUG, TOPIC, GRANT, brief, cwd=where)
        self.assertEqual(run.returncode, 0, "bin/lane-start exits %d: %s" % (run.returncode, run.stderr))
        after = (tree_listing(self.work), tree_listing(where))
        self.assertEqual(before, after, "bin/lane-start wrote a file")

    def test_a_wrong_argument_count_exits_2_with_usage(self):
        run = self.run_helper(SLUG)
        self.assert_refused(run)
        self.assertIn("usage", run.stderr.lower(), "the refusal names no usage: %s" % run.stderr)

    def test_a_missing_brief_file_exits_2_with_usage(self):
        run = self.run_helper(SLUG, TOPIC, GRANT, os.path.join(self.work, "no-such-brief.md"))
        self.assert_refused(run)
        self.assertIn("usage", run.stderr.lower(), "the refusal names no usage: %s" % run.stderr)

    def test_an_empty_grant_line_is_refused_under_lane_effort_pin(self):
        run = self.run_helper(SLUG, TOPIC, "", self.brief("Do the task.\n"), "--repo", OWNER_REPO)
        self.assert_refused(run, "lane-effort-pin")

    def test_a_slug_with_an_underscore_or_a_capital_is_refused_under_lane_title_slug(self):
        for slug in ("fan_settings", "Fan-Settings"):
            with self.subTest(slug=slug):
                run = self.run_helper(slug, TOPIC, GRANT, self.brief("Do the task.\n"), "--repo", OWNER_REPO)
                self.assert_refused(run, "lane-title-slug")

    def test_a_brief_that_names_a_bare_session_id_is_refused_under_brief_ids_in_roster(self):
        run = self.run_helper(SLUG, TOPIC, GRANT, self.brief("Report to session_4711 when done.\n"), "--repo", OWNER_REPO)
        self.assert_refused(run, "brief-ids-in-roster")

    def carrier_transcript(self, step, repo=OWNER_REPO):
        """A transcript whose whole list read shows one live lane, CARRIER_ID, on `step` in `repo`."""
        row = {"id": CARRIER_ID, "title": "a lane session", "session_status": "SESSION_STATUS_RUNNING",
               "tags": ["cs-build:lane", "cs-step:" + step, "cs-repo:" + repo]}
        path = os.path.join(self.work, "carrier-%s.jsonl" % step)
        write_list_transcript(path, [row])
        return path

    def test_a_transcript_with_a_live_lane_on_the_step_refuses_the_start_under_lane_step_dup(self):
        for step in (SLUG, FULL_SLUG):
            with self.subTest(step=step):
                transcript = self.carrier_transcript(step)
                run = self.run_helper(step, TOPIC, GRANT, self.brief("Do the task.\n"), "--repo", OWNER_REPO,
                                      "--transcript", transcript)
                self.assert_refused(run, "lane-step-dup")
                self.assertIn(CARRIER_ID, run.stderr, "the refusal names no live lane that carries the step: %s" % run.stderr)

    def test_a_transcript_whose_live_lane_holds_another_step_or_repo_lets_the_start_print(self):
        for step, repo in (("other-step", OWNER_REPO), (SLUG, "other/repo")):
            with self.subTest(step=step, repo=repo):
                fields = self.start("--repo", OWNER_REPO, "--transcript", self.carrier_transcript(step, repo))
                self.assertIn("cs-step:" + SLUG, fields["tags"], "the printed start does not carry its own step")

    def test_a_transcript_with_no_whole_list_read_refuses_the_start_as_unknown(self):
        no_read = os.path.join(self.work, "no-read.jsonl")
        open(no_read, "w", encoding="utf-8").close()
        missing = os.path.join(self.work, "no-such-transcript.jsonl")
        for path in (no_read, missing):
            with self.subTest(transcript=os.path.basename(path)):
                run = self.run_helper(SLUG, TOPIC, GRANT, self.brief("Do the task.\n"), "--repo", OWNER_REPO,
                                      "--transcript", path)
                self.assert_refused(run, "lane-step-dup")
                self.assertIn("does not prove", run.stderr, "the refusal does not say the step is unproven: %s" % run.stderr)

    def test_the_repo_defaults_to_the_checkout_when_a_transcript_is_given(self):
        where = self.checkout()
        run = self.run_helper(SLUG, TOPIC, GRANT, self.brief("Do the task.\n"), "--transcript",
                              self.carrier_transcript(SLUG), cwd=where)
        self.assert_refused(run, "lane-step-dup")

    def test_the_helper_source_holds_no_literal_copy_of_a_lane_constant(self):
        self.assertTrue(os.path.isfile(HELPER), "bin/lane-start is missing, so its source cannot be checked")
        with open(HELPER, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=HELPER)
        copies = []
        for node in ast.walk(tree):
            text = str_value(node)
            if text is None:
                continue
            if text in (LANE_EFFORT_VALUE, LANE_MODEL_VALUE, LANE_BRIEF_VALUE) or text.startswith(TAG_PREFIXES):
                copies.append(text)
        self.assertEqual(copies, [], "bin/lane-start holds literal copies of lane constants: %r" % copies)

    def test_a_windows_wrapper_sits_beside_the_helper(self):
        self.assertTrue(os.path.isfile(WRAPPER), "bin/lane-start.cmd is missing; bin/claude-role has one")


class SharedConstants(unittest.TestCase):
    """The constants the helper and the guard read live in hooks/shared_names.py, once. Each case names one cause."""

    def shared_value(self, name):
        for bound, value in module_assigns(SHARED_NAMES):
            if bound == name:
                return str_value(value)
        return None

    def test_shared_names_defines_lane_effort_as_medium(self):
        self.assertEqual(self.shared_value("LANE_EFFORT"), LANE_EFFORT_VALUE,
                         "hooks/shared_names.py defines no LANE_EFFORT of medium, so the helper and the guard share none")

    def test_shared_names_defines_lane_model_as_sonnet(self):
        self.assertEqual(self.shared_value("LANE_MODEL"), LANE_MODEL_VALUE,
                         "hooks/shared_names.py defines no LANE_MODEL of sonnet, so the helper and the guard share none")

    def test_shared_names_defines_the_lane_brief_marker(self):
        self.assertEqual(self.shared_value("LANE_BRIEF_MARKER"), LANE_BRIEF_VALUE,
                         "hooks/shared_names.py defines no LANE_BRIEF_MARKER of Lane brief:")

    def test_the_guard_holds_no_literal_lane_effort(self):
        literal = [name for name, value in module_assigns(GUARD_SOURCE)
                   if name == "LANE_EFFORT" and str_value(value) is not None]
        self.assertEqual(literal, [], "hooks/guard.py assigns its own literal LANE_EFFORT, not the one in shared_names")

    def test_the_guard_takes_lane_effort_from_shared_names(self):
        self.assertIn("LANE_EFFORT", imported_from_shared_names(GUARD_SOURCE),
                      "hooks/guard.py does not import LANE_EFFORT from shared_names, so lint/check_agent_models.py reads a copy")

    def test_the_guard_merge_holds_no_literal_brief_marker(self):
        literal = [name for name, value in module_assigns(GUARD_MERGE_SOURCE)
                   if name == "LANE_BRIEF_MARKER" and str_value(value) is not None]
        self.assertEqual(literal, [], "hooks/guard_merge.py assigns its own literal LANE_BRIEF_MARKER")

    def test_the_guard_merge_holds_no_literal_tag_prefix(self):
        literal = [name for name, value in module_assigns(GUARD_MERGE_SOURCE)
                   if str_value(value) in ("cs-step:", "cs-repo:")]
        self.assertEqual(literal, [], "hooks/guard_merge.py holds literal tag prefixes in %s, not the ones in shared_names"
                         % ", ".join(literal))


class HandoffPremise(unittest.TestCase):
    """Change 3: the handoff template tells a session that a lane-start premise names the helper, and carries no recipe."""

    def read(self, path):
        self.assertTrue(os.path.isfile(path), "%s is missing" % os.path.relpath(path, REPO))
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_the_handoff_premise_names_the_helper(self):
        lines = [line for line in self.read(HANDOFF_PROMPT).splitlines() if "bin/lane-start" in line]
        self.assertTrue(lines, "hooks/precompact_handoff_prompt.md names no bin/lane-start: a lane-start premise has no pointer")

    def test_the_handoff_prompt_carries_no_lane_start_recipe(self):
        recipes = [(unit, recipe_markers(unit)) for unit in units_of(self.read(HANDOFF_PROMPT)) if recipe_markers(unit)]
        self.assertEqual(recipes, [], "hooks/precompact_handoff_prompt.md carries a lane-start recipe: %r" % recipes[:1])


class ProjectOpsTemplates(unittest.TestCase):
    """Change 3: the project-ops templates carry no lane-start recipe. Each file is first read and checked for its anchor, so
    a template that moves cannot pass by reading nothing."""

    ANCHORS = {"operating-model.md": "Coordinator", "brief.md": "Lane brief:", "role-handoff.md": "handoff"}

    def test_each_template_is_read_and_holds_its_anchor(self):
        for name, anchor in sorted(self.ANCHORS.items()):
            path = os.path.join(TEMPLATES, name)
            self.assertTrue(os.path.isfile(path), "%s is missing" % os.path.relpath(path, REPO))
            with open(path, encoding="utf-8") as handle:
                self.assertIn(anchor, handle.read(), "%s no longer holds its anchor %r" % (name, anchor))

    def test_no_template_carries_a_lane_start_recipe(self):
        found = []
        for name in sorted(self.ANCHORS):
            with open(os.path.join(TEMPLATES, name), encoding="utf-8") as handle:
                for unit in units_of(handle.read()):
                    markers = recipe_markers(unit)
                    if markers:
                        found.append("%s: %s" % (name, "; ".join(markers)))
        self.assertEqual(found, [], "a project-ops template carries a lane-start recipe, to be a pointer to bin/lane-start: %r"
                         % found)


if __name__ == "__main__":
    unittest.main(verbosity=2)
