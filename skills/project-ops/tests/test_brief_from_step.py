#!/usr/bin/env python3
"""Cases for skills/project-ops/scripts/brief_from_step.py and templates/brief.md. Standard library only.

    python3 skills/project-ops/tests/test_brief_from_step.py

The tool fills the one brief template from a roadmap step file (roadmap/data/steps/<slug>.json on the `roadmap`
branch) and the rulings that name the step (roadmap/rulings/*.json, read through lint/ruled_store.py). Each case builds
a real git repo under this run's folder (lint/_test_temp.py) with the store helpers of lint/test_ruled_store.py, which
this file imports as `fixture`. BRIEF_FROM_STEP_UNDER_TEST overrides the module path, as a stub or mutant run needs.

The module loads inside each case, after the case asserts that the file exists. A checkout without the module fails
each case on that assert, never on an import error. The template cases read templates/brief.md and need no module.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(1, os.path.join(SKILL, "..", "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import test_ruled_store as fixture  # noqa: E402  the store helpers, the one home (lint/test_ruled_store.py)
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
from test_scaffold import NEGATION, has_sentence, sentences  # noqa: E402  the one home of sentence splitting

MODULE = os.path.abspath(os.environ.get("BRIEF_FROM_STEP_UNDER_TEST")
                         or os.path.join(SKILL, "scripts", "brief_from_step.py"))
TEMPLATE = os.path.join(SKILL, "templates", "brief.md")  # the one template
PATH = re.compile(r"[\w./~-]+\.(?:py|md|json|sh|mjs|js|yml|yaml|html|txt|tmpl)\b")  # a file name in the text
RUN_FOLDER = None  # made in setUpModule

REF = "roadmap"
SLUG = "write-brief-tool"
TITLE = "Fill the lane brief from a step file"
WHY = "Hand-written briefs drop the owner's rulings, so lanes rebuild decided work."
SOURCE = "page item 412, Nov 13"
GRANT = "Grant: <owner words>, <time>"
FILES_MARKER = "<coordinator names the files>"
CHECK_MARKER = "<coordinator names the check that proves done>"
PARAPHRASE = "(paraphrase, no owner quote)"
FULL = 30  # the full-size store: one step with this many rulings
# The word count of the old templates/brief.md, the one the builder rewrote: 821 words by wc -w.
# Pinned, so that rewrite does not move the cap.
BASELINE_WORDS = 821
PASTED_LINES = 40  # a pasted file body in a step note: the brief never carries it
PATH_IN_NOTE = "skills/project-ops/scripts/brief_from_step.py"  # a path in a note: Files keeps it
SECTIONS = ["Task", "Files", "Rulings", "Failure classes", "Done-check", "Report cap"]  # after Grant and Lane brief
# What a spawn already gets from hooks/agent_brief.py. The brief never restates these.
# Co-Authored-By comes only to the types that commit.
RESTATED = ["Standing rules for this agent", "Co-Authored-By", "git stash", "Never run git"]

Q_OPEN = "Coordinator ruling, 2026-11-08 07:16 CST: the brief is built from the step, never hand-written."
Q_CLOSED = "Owner: one brief template, filled by the tool and never a second copy."
Q_OTHER = "Owner: unrelated work waits for the drain."
Q_ID = "Owner: hold new work until tracking lands."
Q_ALIAS = "Owner: the restart plan governs the drain."
Q_UNNAMED = "Owner: a ruling that no step names."
PARA_TEXT = "Owner: keep the brief to one template."
Q_LONG = ('Yeah approved A, and the brief is "built from the step", its rulings quoted word for word, never retyped, '
          'so each quote stays exactly as the owner typed it.')
Q_DASH = 'Keep "one template" — the tool fills it, and nothing else writes a brief.'
AT_OPEN = "2026-11-08T07:16:00-06:00"
AT_CLOSED = "2026-11-09T09:30:00-06:00"
AT_OTHER = "2026-11-10T10:10:00-06:00"
AT_ID = "2026-11-11T11:11:00-06:00"
AT_ALIAS = "2026-11-12T12:12:00-06:00"
AT_UNNAMED = "2026-11-12T13:13:00-06:00"
AT_PARA = "2026-11-12T14:14:00-06:00"
AT_LONG = "2026-11-12T15:15:00-06:00"
AT_DASH = "2026-11-12T16:16:00-06:00"
SRC_OPEN = "owner chat, 07:16 CST Nov 8"
SRC_CLOSED = "PR 2015 body, Nov 9"
SRC_OTHER = "page item 9"
SRC_ID = "page item 10"
SRC_ALIAS = "page item 11"
SRC_UNNAMED = "page item 12"
SRC_PARA = "page item 13"
SRC_LONG = "page item 14"
SRC_DASH = "page item 15"
Q_R9 = "Owner: rule nine holds for every lane."
Q_R55 = "Owner: rule fifty-five holds for every lane."
Q_EXACT_ALIAS = "Owner: the exact alias governs the drain."
Q_ALIAS_CAP = "Owner: the capital alias governs the drain."
Q_ALIAS_LOW = "Owner: the lowercase alias governs the drain."
Q_RELAYED = "Owner words relayed by the coordinator: keep the drain small."
AT_RELAYED = "2026-11-12T17:17:00-06:00"
RELAYED = "relayed by lane bg-tail-loses-verdict, 11:51 CST Nov 13; not a direct owner quote"
UNREADABLE = "roadmap/rulings/unreadable-one.json"  # a ruling file that is not JSON
MODEL_NAME = re.compile(r"sonnet|haiku|opus", re.I)
# The R9 ruling's own words and time, copied from roadmap/rulings/r9.json on origin/roadmap,
# so no test reads that branch.
R9_WORDS = ("passes round 1 is done", "fixed under a fix verifier waits for round 3", "15:44")
SPAWN_HEAD = "Agent spawn brief head"  # the heading of the block a lane copies into a spawn brief
PROVED = "proved at batch CI"  # the Done-check form for a check only batch CI can prove
DONE_TEXT = "run the brief suite and its lint"  # a step's done_check text
CI_ONLY_TEXT = "the full checks job on the batch branch"  # a step's done_check text when ci_only is true
MARKER_FORMS = ("Guard or check: yes", "Fix check", "Round 2 of 3", "Round 3 of 3", "Audit:")
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.abspath(os.path.join(HERE, "..", "..", "..", "hooks", "guard.py"))
# The real decision record the guard reads for the role table and the round rows.
DECISION_RECORD = os.path.abspath(os.path.join(HERE, "..", "..", "..", "docs", "decisions", "agent-model-cap.md"))


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def load_module():
    spec = importlib.util.spec_from_file_location("brief_from_step", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cli(*args):
    return _nowindow.run([sys.executable, MODULE, *args], capture_output=True, text=True, env=fixture.ENV,
                         timeout=60)


def step_doc(**over):
    """A step file with the fields the tool reads. It has no files, done-check or failure-class field."""
    body = {"title": TITLE, "why": WHY, "source": SOURCE, "status": "ready", "phase": "next", "order": 1,
            "note": "Coordinator note: started from the roadmap page."}
    body.update(over)
    return body


def read_template():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def section(text, heading):
    """The body of the `## <heading>` section of a brief, or None."""
    m = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % re.escape(heading), text, re.M | re.S)
    return m.group(1) if m else None


def headings(text):
    """The `## ` headings of a brief or a template, in order."""
    return re.findall(r"^## (.+?)\s*$", text, re.M)


def two_rulings():
    return {
        "open-one": fixture.entry("open-one", step=SLUG, quote=Q_OPEN, at=AT_OPEN, source=SRC_OPEN),
        "closed-one": fixture.entry("closed-one", step=SLUG, quote=Q_CLOSED, at=AT_CLOSED, source=SRC_CLOSED,
                                    status="closed"),
    }


def note_with_block():
    """A step note that names one path and pastes a 40-line file body in a code fence."""
    body = "\n".join("    value_%02d = compute(%d)" % (n, n) for n in range(PASTED_LINES))
    return "Coordinator note: edit %s only.\n\n```python\n%s\n```\n" % (PATH_IN_NOTE, body)


def unreadable_count(repo):
    """The ruling files in the store's folder that read_store does not return: the folder's list less the entries."""
    listed = fixture.git(repo, "ls-tree", "--name-only", "refs/heads/" + REF, "roadmap/rulings/")
    files = [name for name in listed.split("\n") if name.endswith(".json")]
    return len(files) - len(fixture.ruled_store.read_store(repo, REF)[0])


def spawn_block(out):
    """The lines after the `Agent spawn brief head` heading (plain, or with # marks), or None when there is none."""
    lines = out.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lstrip("#").strip() == SPAWN_HEAD:
            return lines[index + 1:]
    return None


def is_marker_line(line):
    return any(line.startswith(form) for form in MARKER_FORMS)


def fenced_pairs(lines):
    """(line, inside a ``` fence) for each line; a fence line counts as inside."""
    fenced, pairs = False, []
    for line in lines:
        if line.strip().startswith("```"):
            fenced = not fenced
            pairs.append((line, True))
        else:
            pairs.append((line, fenced))
    return pairs


def spawn_brief(block, marker=None):
    """The text a lane copies into a spawn brief: `marker` on the first line, then the block's own lines without its
    marker-form listing. The listing is left out so the guard reads only the marker the lane chose."""
    kept = [line for line in block if line.strip() and line.strip() != "none" and not is_marker_line(line)]
    return "\n".join(([marker] if marker else []) + kept)


def guard_reason(config, prompt, model="sonnet", role="reviewer"):
    """The real guard's answer to one Agent spawn, as Claude Code reads it: "" for an allow, else the deny reason."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": config,
               "tool_input": {"subagent_type": role, "model": model, "prompt": prompt}}
    env = dict(fixture.ENV, CLAUDE_CONFIG_DIR=config)
    env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)  # the env pin lifts the refusal; the cases must not inherit it
    done = _nowindow.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True,
                         env=env, timeout=60)
    text = done.stdout.strip()
    if not text:
        return ""
    try:
        body = json.loads(text)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return "unreadable guard output: %s" % text[:200]
    return body.get("permissionDecisionReason") or body.get("permissionDecision") or "unreadable guard output"


def template_tail():
    """The template from its Failure classes heading to the end: the lines that name the process."""
    m = re.search(r"^## Failure classes", read_template(), re.M)
    return read_template()[m.start():] if m else ""


def tail_has(*patterns):
    """True when one sentence of the template's tail matches every pattern."""
    return has_sentence(sentences(template_tail()), *patterns)


class BriefCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="brief_from_step_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)

    def make_repo(self, step=None, rulings=None, extra=None):
        """A repo whose `roadmap` branch holds the step file, the rulings and any extra {path: text} files."""
        repo = fixture.init_repo(os.path.join(self.root, "repo"))
        files = dict(extra or {})
        if step is not None:
            files["roadmap/data/steps/%s.json" % SLUG] = json.dumps(step, indent=2)
        files.update(fixture.ruling_files(rulings or {}))
        fixture.point_ref(repo, "refs/heads/" + REF, files, self.root)
        return repo

    def store_state(self, repo):
        return fixture.ruled_store.read_store(repo, REF)[1]

    def build(self, repo, slug=SLUG):
        self.assertTrue(os.path.exists(MODULE), "the brief module is missing: %s" % MODULE)
        return load_module().build(slug, repo, REF)

    def assert_unknown(self, repo, state):
        """The brief still prints, and carries the unknown line for the store state."""
        self.assertEqual(self.store_state(repo), state, "control: the store does not read as %s" % state)
        out = self.build(repo)
        self.assertIn("Rulings: unknown (store %s)" % state, [line.strip() for line in out.splitlines()],
                      "a store that reads as %s is not reported as unknown" % state)
        self.assertIn(TITLE, out, "the brief did not print with the store %s" % state)
        self.assertNotIn("no rulings", out.lower(), "a store that reads as %s reads as no rulings" % state)


class RulingLines(BriefCase):

    def test_open_and_closed_rulings_for_the_step_show_quote_time_and_source(self):
        repo = self.make_repo(step=step_doc(), rulings={
            "open-one": fixture.entry("open-one", step=SLUG, quote=Q_OPEN, at=AT_OPEN, source=SRC_OPEN),
            "closed-one": fixture.entry("closed-one", step=SLUG, quote=Q_CLOSED, at=AT_CLOSED, source=SRC_CLOSED,
                                        status="closed"),
        })
        self.assertEqual(self.store_state(repo), "ok", "control: the store does not read as ok")
        out = self.build(repo)
        self.assertIn(Q_OPEN, out, "the open ruling's quote is missing or not verbatim")
        self.assertIn(AT_OPEN, out, "the open ruling's at time is missing")
        self.assertIn(SRC_OPEN, out, "the open ruling's source is missing")
        self.assertIn(Q_CLOSED, out, "the closed ruling for the step is dropped; a landed ruling still governs")
        self.assertIn(AT_CLOSED, out, "the closed ruling's at time is missing")
        self.assertIn(SRC_CLOSED, out, "the closed ruling's source is missing")

    def test_ruling_without_quote_is_marked_paraphrase(self):
        repo = self.make_repo(step=step_doc(), rulings={
            "paraphrase-one": fixture.entry("paraphrase-one", step=SLUG, quote=None, ruling=PARA_TEXT,
                                            at=AT_PARA, source=SRC_PARA),
        })
        out = self.build(repo)
        shown = [line for line in out.splitlines() if PARA_TEXT in line]
        self.assertTrue(shown, "the ruling without a quote is missing its text")
        self.assertTrue(any(PARAPHRASE in line for line in shown),
                        "the ruling without a quote is not marked %s on its line" % PARAPHRASE)
        self.assertNotIn('"%s"' % PARA_TEXT, out, "the paraphrase is in quotes, as if it were the owner's words")

    def test_ruling_for_another_step_is_left_out(self):
        repo = self.make_repo(step=step_doc(), rulings={
            "own-one": fixture.entry("own-one", step=SLUG, quote=Q_OPEN, at=AT_OPEN, source=SRC_OPEN),
            "other-one": fixture.entry("other-one", step="some-other-step", quote=Q_OTHER, at=AT_OTHER,
                                       source=SRC_OTHER),
        })
        out = self.build(repo)
        self.assertIn(Q_OPEN, out, "the step's own ruling is missing")
        self.assertNotIn(Q_OTHER, out, "a ruling for another step is shown")
        self.assertNotIn(AT_OTHER, out, "a ruling for another step is shown, by its at time")

    def test_ruling_named_in_note_by_id_or_alias_is_shown(self):
        repo = self.make_repo(step=step_doc(note="Governed by drain-first-hold and by R66."), rulings={
            "drain-first-hold": fixture.entry("drain-first-hold", step="other-step", quote=Q_ID, at=AT_ID,
                                              source=SRC_ID),
            "backlog-drain-plan": fixture.entry("backlog-drain-plan", step="other-step", aliases=["R66"],
                                                quote=Q_ALIAS, at=AT_ALIAS, source=SRC_ALIAS),
            "unnamed-one": fixture.entry("unnamed-one", step="other-step", quote=Q_UNNAMED, at=AT_UNNAMED,
                                         source=SRC_UNNAMED),
        })
        out = self.build(repo)
        self.assertIn(Q_ID, out, "the ruling the note names by id is missing")
        self.assertIn(Q_ALIAS, out, "the ruling the note names by alias R66 is missing")
        self.assertNotIn(Q_UNNAMED, out, "a ruling the note does not name is shown")

    def test_capital_ruling_id_in_note_prints_the_lowercase_entry(self):
        note = "Express under R55; see R9 here. Governed by drain-first-hold."
        repo = self.make_repo(step=step_doc(note=note), rulings={
            "drain-first-hold": fixture.entry("drain-first-hold", step="other-step", quote=Q_ID, at=AT_ID,
                                              source=SRC_ID),
            "r55": fixture.entry("r55", step="other-step", quote=Q_R55),
            "r9": fixture.entry("r9", step="other-step", quote=Q_R9),
        })
        self.assertEqual(self.store_state(repo), "ok", "control: the store does not read as ok")
        out = self.build(repo)
        self.assertIn(Q_ID, out, "control: an exact-case id named in the note does not print its ruling")
        missing = [quote for quote in (Q_R55, Q_R9) if quote not in out]
        self.assertEqual(missing, [], "a ruling id written in capitals in a note does not print its lowercase entry")

    def test_alias_written_in_another_case_than_the_stored_alias_matches(self):
        repo = self.make_repo(step=step_doc(note="Governed by R88, r66 and R77."), rulings={
            "exact-alias-plan": fixture.entry("exact-alias-plan", step="other-step", aliases=["R88"],
                                              quote=Q_EXACT_ALIAS),
            "backlog-drain-plan": fixture.entry("backlog-drain-plan", step="other-step", aliases=["R66"],
                                                quote=Q_ALIAS_CAP),
            "lower-alias-plan": fixture.entry("lower-alias-plan", step="other-step", aliases=["r77"],
                                              quote=Q_ALIAS_LOW),
        })
        self.assertEqual(self.store_state(repo), "ok", "control: the store does not read as ok")
        out = self.build(repo)
        self.assertIn(Q_EXACT_ALIAS, out, "control: an alias named in the note as stored does not print its ruling")
        missing = [quote for quote in (Q_ALIAS_CAP, Q_ALIAS_LOW) if quote not in out]
        self.assertEqual(missing, [], "an alias written in another case than its stored value is not matched")

    def test_id_inside_a_longer_id_or_word_is_not_shown(self):
        repo = self.make_repo(step=step_doc(note="Governed by R99, r9x and drain-first-hold."), rulings={
            "drain-first-hold": fixture.entry("drain-first-hold", step="other-step", quote=Q_ID, at=AT_ID,
                                              source=SRC_ID),
            "r9": fixture.entry("r9", step="other-step", quote=Q_R9),
        })
        self.assertEqual(self.store_state(repo), "ok", "control: the store does not read as ok")
        out = self.build(repo)
        self.assertIn(Q_ID, out, "control: an exact-case id named in the note does not print its ruling")
        self.assertNotIn(Q_R9, out, "the ruling r9 prints for a note that names only R99 and r9x, longer ids or words")

    def test_clean_pass_every_quote_is_a_verbatim_substring(self):
        repo = self.make_repo(step=step_doc(), rulings={
            "long-one": fixture.entry("long-one", step=SLUG, quote=Q_LONG, at=AT_LONG, source=SRC_LONG),
            "dash-one": fixture.entry("dash-one", step=SLUG, quote=Q_DASH, at=AT_DASH, source=SRC_DASH),
        })
        out = self.build(repo)
        for quote in (Q_LONG, Q_DASH):
            self.assertIn(quote, out, "a quote is not verbatim in the brief: %r" % quote[:40])

    def test_full_size_store_shows_every_ruling_for_the_step(self):
        quotes = {"ruling-%02d" % n: "Owner: rule %02d holds." % n for n in range(1, FULL + 1)}
        repo = self.make_repo(step=step_doc(), rulings={
            rid: fixture.entry(rid, step=SLUG, quote=quote, at=AT_OPEN, source=SRC_OPEN)
            for rid, quote in quotes.items()})
        out = self.build(repo)
        missing = [quote for quote in quotes.values() if quote not in out]
        self.assertEqual(missing, [], "%d of %d rulings for the step are missing" % (len(missing), FULL))


class StepFields(BriefCase):

    def test_step_fields_and_grant_line_fill_the_brief(self):
        repo = self.make_repo(step=step_doc(title=TITLE, why=WHY, source=SOURCE))
        out = self.build(repo)
        lines = out.splitlines()
        self.assertTrue(lines, "the brief is empty")
        self.assertEqual(lines[0], GRANT, "the first line is not the Grant line left for the coordinator")
        self.assertTrue(any(line.startswith("Lane brief: %s." % SLUG) for line in lines),
                        "no line reads 'Lane brief: %s.'" % SLUG)
        task = section(out, "Task")
        self.assertIsNotNone(task, "the brief has no ## Task section")
        self.assertIn(TITLE, task, "the step title is not in Task")
        self.assertIn(WHY, task, "the step's why is not in Task")
        self.assertIn(SOURCE, out, "the step's source is not in the brief")

    def test_files_and_done_check_are_markers_the_tool_does_not_invent(self):
        step = step_doc()
        repo = self.make_repo(step=step)
        out = self.build(repo)
        self.assertIn(FILES_MARKER, out, "the files marker is missing")
        self.assertIn(CHECK_MARKER, out, "the done-check marker is missing")
        allowed = set(PATH.findall(read_template() + json.dumps(step)))
        invented = sorted(set(PATH.findall(out)) - allowed)
        self.assertEqual(invented, [], "the brief names a file that no input holds")


class StoreStates(BriefCase):

    def test_absent_store_still_prints_and_says_unknown(self):
        self.assert_unknown(self.make_repo(step=step_doc()), "absent")

    def test_unreadable_store_still_prints_and_says_unknown(self):
        # git lists a folder named like a ruling file, but it is a tree, not a blob, so no ruling reads.
        repo = self.make_repo(step=step_doc(), extra={"roadmap/rulings/broken.json/inner.txt": "not a ruling"})
        self.assert_unknown(repo, "unreadable")

    def test_store_with_no_ruling_for_the_step_is_not_unknown(self):
        repo = self.make_repo(step=step_doc(), rulings={
            "elsewhere": fixture.entry("elsewhere", step="other-step", quote=Q_OTHER, at=AT_OTHER, source=SRC_OTHER),
        })
        self.assertEqual(self.store_state(repo), "ok", "control: the store does not read as ok")
        out = self.build(repo)
        self.assertIn(TITLE, out, "the brief did not print for a step with no rulings")
        self.assertNotIn("Rulings: unknown", out, "a readable store with no ruling for the step reads as unknown")


class Cli(BriefCase):

    def test_cli_prints_the_brief_for_a_known_slug(self):
        repo = self.make_repo(step=step_doc())
        self.assertTrue(os.path.exists(MODULE), "the brief module is missing: %s" % MODULE)
        done = cli(SLUG, "--repo", repo, "--ref", REF)
        self.assertEqual(done.returncode, 0, "a known slug did not exit 0: %s" % done.stderr.strip())
        self.assertIn(TITLE, done.stdout, "the CLI did not print the step's title")

    def test_unknown_slug_exits_1_and_names_the_slug(self):
        repo = self.make_repo(step=step_doc())
        self.assertTrue(os.path.exists(MODULE), "the brief module is missing: %s" % MODULE)
        done = cli("no-such-step", "--repo", repo, "--ref", REF)
        self.assertEqual(done.returncode, 1, "an unknown slug did not exit 1 (exit %d)" % done.returncode)
        self.assertIn("no-such-step", done.stdout + done.stderr, "the message does not name the unknown slug")


class FixedLayout(BriefCase):

    def test_section_headings_are_the_fixed_list_in_order_for_any_step(self):
        cases = [
            ("bare", step_doc(), None),
            ("pasted-note", step_doc(note=note_with_block()), None),
            ("with-rulings", step_doc(title="A longer title, " * 3, why=WHY * 2), two_rulings()),
        ]
        for label, step, rulings in cases:
            out = self.build(self.make_repo(step=step, rulings=rulings))
            self.assertEqual(headings(out), SECTIONS,
                             "the brief's headings are not the fixed list in order, for step %s" % label)

    def test_files_holds_the_path_and_no_pasted_block_reaches_the_output(self):
        out = self.build(self.make_repo(step=step_doc(note=note_with_block())))
        files = section(out, "Files")
        self.assertIsNotNone(files, "the brief has no ## Files section")
        self.assertIn(PATH_IN_NOTE, files, "the path the note names is not in Files")
        self.assertNotIn("```python", out, "the step note's code fence reaches the output")
        leaked = [n for n in range(PASTED_LINES) if "value_%02d" % n in out]
        self.assertEqual(leaked, [], "%d of %d lines of the pasted block reach the output"
                         % (len(leaked), PASTED_LINES))

    def test_output_restates_nothing_the_agent_already_loads(self):
        out = self.build(self.make_repo(step=step_doc(), rulings=two_rulings()))
        for phrase in RESTATED:
            self.assertNotIn(phrase, out, "the brief restates %r, which the agent already loads" % phrase)

    def test_two_ruling_brief_is_at_most_sixty_percent_of_the_template_words(self):
        out = self.build(self.make_repo(step=step_doc(), rulings=two_rulings()))
        out_words = len(out.split())
        self.assertLessEqual(out_words, 0.6 * BASELINE_WORDS,
                             "the brief has %d words, over 60%% of the %d-word baseline"
                             % (out_words, BASELINE_WORDS))


class TemplateTail(unittest.TestCase):
    """The template's tail, read as text. These cases need no module: the template is the old code's."""

    def test_template_keeps_the_section_headings_in_order(self):
        self.assertEqual(headings(read_template()), SECTIONS,
                         "the template's section headings are not the fixed list in order")
        lines = read_template().splitlines()
        self.assertTrue(lines and lines[0].startswith("Grant:"), "the template does not open with the Grant line")
        self.assertTrue(any(line.startswith("Lane brief:") for line in lines), "the template has no Lane brief line")

    def test_red_first_line_is_in_the_template(self):
        self.assertTrue(tail_has(r"\bred first\b"), "the template's tail has no sentence that says red first")

    def test_round_one_review_follows_the_ruling_in_the_store(self):
        self.assertTrue(tail_has(r"\bround[- ]1\b", r"\bruling\b", r"\bstore\b"),
                        "the template's tail has no round-1 review sentence that follows the ruling in the store")

    def test_round_one_review_has_no_round_three(self):
        self.assertTrue(tail_has(r"\bround 3\b", NEGATION), "the template does not say there is no round 3")

    def test_hand_in_is_a_draft_pr_to_the_batch_runner(self):
        self.assertTrue(tail_has(r"\bdraft\b", r"\bPR\b", r"\bbatch runner\b"),
                        "the template has no sentence that hands in a draft PR to the batch runner")

    def test_questions_go_to_triage(self):
        self.assertTrue(tail_has(r"\bquestions?\b", r"\btriage\b"),
                        "the template does not send questions to triage")

    def test_report_cap_in_lines_is_named(self):
        # Already in the template on the base commit: a guard that the rewritten template keeps the cap.
        self.assertTrue(tail_has(r"\bcap\b", r"\blines\b"), "the template does not cap the report in lines")


class TemplateRules(unittest.TestCase):
    """The template's own lines: the cs-topic tag, the fix-round line, no ruling words, the Fences line,
    the practice decisions, models."""

    def test_template_keeps_the_cs_topic_tag_line(self):
        self.assertTrue(any("cs-topic:" in line for line in read_template().splitlines()),
                        "the template has no line naming the cs-topic tag")

    def test_template_says_each_fix_round_is_a_fresh_isolated_spawn(self):
        self.assertIn("fresh isolated spawn", read_template(),
                      "the template does not say each fix round is a fresh isolated spawn")

    def test_template_names_no_ruling_id_and_restates_no_ruling_words(self):
        text = read_template()
        found = re.search(r"\br\d+\b", text, re.I)
        self.assertIsNone(found, "the template names a ruling by id: %s" % (found and found.group(0)))
        for phrase in R9_WORDS:
            self.assertNotIn(phrase, text, "the template restates a ruling's words or time: %r" % phrase)

    def test_task_part_holds_a_fences_line(self):
        task = section(read_template(), "Task")
        self.assertIsNotNone(task, "the template has no ## Task section")
        self.assertTrue(re.search(r"^Fences\b", task, re.M), "the Task part has no Fences line")

    def test_template_names_test_practices_and_merge_practices_on_one_line(self):
        self.assertTrue(any("test-practices" in line and "merge-practices" in line
                            for line in read_template().splitlines()),
                        "no line names the decisions test-practices and merge-practices")

    def test_template_names_no_model_but_the_roadmap_fetch_line(self):
        offenders = [line for line in read_template().splitlines()
                     if MODEL_NAME.search(line) and "refs/heads/roadmap" not in line]
        self.assertEqual(offenders, [], "the template names a model outside the roadmap fetch line")

    def test_template_says_each_agent_runs_its_role_row_in_agent_model_cap(self):
        self.assertTrue(any("agent-model-cap" in line and re.search(r"\brole\b", line, re.I)
                            for line in read_template().splitlines()),
                        "no line says each agent runs its role row in agent-model-cap")

    def test_done_check_says_the_lane_can_run_its_check(self):
        done = section(read_template(), "Done-check")
        self.assertIsNotNone(done, "the template has no ## Done-check section")
        self.assertTrue(has_sentence(sentences(done), r"\bcan run\b", r"\bcheck\b"),
                        "the Done-check part does not say a done check is one the lane can run")

    def test_done_check_names_the_batch_ci_form_and_does_not_fail_the_lane_on_it(self):
        done = section(read_template(), "Done-check")
        self.assertIsNotNone(done, "the template has no ## Done-check section")
        self.assertTrue(has_sentence(sentences(done), r"\bproved at batch CI\b", r"\bfail", NEGATION),
                        "the Done-check part does not say a check only batch CI proves is written 'proved at batch CI' "
                        "and the lane is not failed on it")

    def test_template_holds_no_ruling_id_or_measured_figure(self):
        text = read_template()
        found = re.search(r"\br\d+\b", text, re.I)
        self.assertIsNone(found, "the template names a ruling by id: %s" % (found and found.group(0)))
        self.assertNotIn("%", text, "the template holds a measured figure written as a percent")


class RulingsAndSource(BriefCase):

    def test_unparseable_ruling_file_is_counted_and_not_read_as_none(self):
        repo = self.make_repo(step=step_doc(), extra={UNREADABLE: "{ not json"})
        self.assertEqual(unreadable_count(repo), 1, "control: the store does not hold one unreadable ruling file")
        out = self.build(repo)
        lines = [line.strip() for line in out.splitlines()]
        self.assertIn("Rulings: unknown (1 unreadable ruling file)", lines,
                      "the unreadable ruling file is not counted in the Rulings line")
        self.assertNotIn("None names this step", out, "an unreadable ruling file reads as no ruling")

    def test_unparseable_ruling_file_beside_a_ruling_still_says_unknown(self):
        repo = self.make_repo(step=step_doc(), extra={UNREADABLE: "{ not json"}, rulings={
            "open-one": fixture.entry("open-one", step=SLUG, quote=Q_OPEN, at=AT_OPEN, source=SRC_OPEN)})
        self.assertEqual(unreadable_count(repo), 1, "control: the store does not hold one unreadable ruling file")
        out = self.build(repo)
        self.assertIn(Q_OPEN, out, "the readable ruling for the step is missing")
        self.assertIn("Rulings: unknown (1 unreadable ruling file)", [line.strip() for line in out.splitlines()],
                      "the unreadable ruling file beside a ruling is not counted in the Rulings line")

    def test_step_without_a_source_says_source_unknown(self):
        step = step_doc()
        del step["source"]
        lines = [line.strip() for line in self.build(self.make_repo(step=step)).splitlines()]
        self.assertNotIn("Source:", lines, "the Source line is blank for a step with no source")
        self.assertIn("Source: unknown", lines, "a step with no source does not print Source: unknown")

    def test_relayed_source_prints_on_the_ruling_line_next_to_the_quote(self):
        repo = self.make_repo(step=step_doc(), rulings={
            "relayed-one": fixture.entry("relayed-one", step=SLUG, quote=Q_RELAYED, at=AT_RELAYED, source=RELAYED)})
        out = self.build(repo)
        self.assertIn(Q_RELAYED, out, "the relayed ruling's quote is missing")
        quote_lines = [line for line in out.splitlines() if Q_RELAYED in line]
        self.assertTrue(any(RELAYED in line for line in quote_lines),
                        "the relayed source is not printed on the quote's line")


class SpawnBriefHead(BriefCase):
    """The block a lane copies into a spawn brief, and the real guard's answer to that brief."""

    def setUp(self):
        super().setUp()
        self.config = os.path.join(self.root, "config")
        pointer = os.path.join(self.config, "pointer")
        os.makedirs(os.path.join(pointer, "docs", "decisions"))
        # A copy of the real record in a temp pointer checkout: the guard reads the same file the repo holds.
        shutil.copy(DECISION_RECORD, os.path.join(pointer, "docs", "decisions", "agent-model-cap.md"))
        open(os.path.join(pointer, "CLAUDE.md"), "w", encoding="utf-8").close()
        with open(os.path.join(self.config, "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@%s/CLAUDE.md\n" % pointer.replace(os.sep, "/"))

    def block(self):
        out = self.build(self.make_repo(step=step_doc()))
        block = spawn_block(out)
        self.assertIsNotNone(block, "the output has no Agent spawn brief head block")
        return block

    def test_block_lists_each_marker_form_inside_a_fence_and_none_at_a_line_start_outside_one(self):
        block = self.block()
        self.assertTrue(any(line.strip().startswith("```") for line in block),
                        "the block has no code fence to hold the marker listing")
        pairs = fenced_pairs(block)
        for form in MARKER_FORMS:
            self.assertTrue(any(line.startswith(form) and fenced for line, fenced in pairs),
                            "the block does not list the marker form %r inside a code fence" % form)
            self.assertFalse(any(line.startswith(form) and not fenced for line, fenced in pairs),
                             "the block lists the marker form %r at a line start outside a fence" % form)
        self.assertTrue(any("first line" in line for line, _fenced in pairs),
                        "the block does not say the marker goes on the spawn brief's first line")

    def test_spawn_brief_from_the_block_passes_the_real_guard_with_each_marker(self):
        block = self.block()
        for marker in ("Guard or check: yes", "Fix check", "Round 2 of 3"):
            reason = guard_reason(self.config, spawn_brief(block, marker))
            self.assertEqual(reason, "", "the real guard refused a sonnet reviewer whose first line is %r: %s"
                             % (marker, reason[:200]))

    def test_the_real_guard_refuses_the_same_spawn_without_a_marker(self):
        reason = guard_reason(self.config, spawn_brief(self.block()))
        self.assertTrue(reason.startswith("agent-role-model:"),
                        "the spawn with no marker was not refused by agent-role-model: %r" % reason[:200])

    def test_block_pasted_whole_into_a_builder_spawn_on_opus_is_refused_with_no_first_line_marker(self):
        pasted = "\n".join(self.block())  # the block verbatim, its marker listing included, and no marker of its own
        reason = guard_reason(self.config, pasted, model="opus", role="builder")
        self.assertTrue(reason.startswith("agent-model-cap:"),
                        "the marker listing in the pasted block lifted a builder spawn with no first-line marker: %r"
                        % reason[:200])


class DoneCheckFields(BriefCase):
    """The optional step fields done_check and ci_only fill the Done-check line; the note's prose never does."""

    def done_check_body(self, out):
        body = section(out, "Done-check")
        self.assertIsNotNone(body, "the brief has no ## Done-check section")
        return body

    def test_done_check_field_prints_on_the_done_check_line(self):
        out = self.build(self.make_repo(step=step_doc(done_check=DONE_TEXT)))
        self.assertIn(DONE_TEXT, self.done_check_body(out), "the Done-check part does not print the step's done_check")
        self.assertNotIn(PROVED, out, "a done_check without ci_only is written as proved at batch CI")
        self.assertNotIn(CHECK_MARKER, out, "the marker stays though the step names its done check")

    def test_ci_only_field_reads_proved_at_batch_ci_with_the_text(self):
        out = self.build(self.make_repo(step=step_doc(done_check=CI_ONLY_TEXT, ci_only=True)))
        lines = self.done_check_body(out).splitlines()
        self.assertTrue(any(PROVED in line and CI_ONLY_TEXT in line for line in lines),
                        "no Done-check line reads 'proved at batch CI' with the step's done_check text")

    def test_no_field_keeps_the_done_check_marker(self):
        out = self.build(self.make_repo(step=step_doc()))
        self.assertIn(CHECK_MARKER, self.done_check_body(out), "the Done-check part lost the coordinator marker")
        self.assertNotIn(PROVED, out, "a step with no field reads as proved at batch CI")

    def test_note_prose_never_sets_the_done_check(self):
        note = "Batch CI proves the rest of this step; see the CI run on the batch branch."
        out = self.build(self.make_repo(step=step_doc(note=note)))
        self.assertIn(CHECK_MARKER, self.done_check_body(out), "the note's prose replaced the Done-check marker")
        self.assertNotIn(PROVED, out, "the note's prose set the proved at batch CI form")


if __name__ == "__main__":
    unittest.main(verbosity=2)
