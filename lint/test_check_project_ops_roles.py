#!/usr/bin/env python3
"""Cases for lint/check_project_ops_roles.py. Run: python3 lint/test_check_project_ops_roles.py

Each session role that the session-roles sentence of the session-tiers record names needs a role text in
skills/project-ops/templates/operating-model.md and a brief template in skills/project-ops/templates/.
These cases pin the check that enforces it.

Interface the check must meet (the builder builds to it):
- A standalone script. It finds the repo from its own path, as lint/check_skill_model_rows.py does. It reads
  the record in the folder layout.path(ROOT, "decisions") gives (lint/layout.py), and the templates folder
  skills/project-ops/templates/ with its operating-model.md.
- Roles: the sentence that starts `The session roles are the same on local and cloud:` in the record, read
  outside fenced blocks and multi-line HTML comments, up to its closing period. The anchor may wrap at any line
  break or bullet indent between its words. Drop any parenthetical first: a period inside one does not end the
  sentence. Split on commas and a final `and`. "batch runner" is one role, and a hyphen stands for a space, so
  "batch-runner" is the same role. A list with commas and no final `and` ends at a stray period: it exits 2 and
  names the record, and never drops roles silently. A role the sentence does not name needs no role text and no
  template. A missing sentence, or one that gives no roles, exits 2 and names the record.
- Case: a capitalised role in the sentence reads as its lowercase name. `Lane` is the role `lane`, so its template is
  brief.md, and a problem line names `lane`.
- Role text: a line that starts `- **<Role>.**` in operating-model.md, outside fenced blocks and multi-line HTML
  comments. The marker needs words after it: a bare `- **Arbiter.**` is no role text. The role's first letter is
  capitalised in the text; match case-insensitively, and a hyphen matches a space in either direction. A role named
  in prose is not role text.
- Brief template: lane -> templates/brief.md; every other role -> templates/brief-<role, spaces as hyphens>.md
  (e.g. brief-batch-runner.md). It must exist and hold text: whitespace alone is empty. A template for a role the
  sentence does not name is fine.
- Exit 0 and print nothing when clean. Exit 1, one line per problem, naming the role and the missing thing:
  "role `consultant`: no role text", "role `arbiter`: no brief template templates/brief-arbiter.md".
- Exit 2, naming the path, on unreadable input: the record, operating-model.md, or the templates folder. A missing
  brief template exits 1. A missing folder exits 2, as a missing skills/ folder does in
  lint/check_skill_model_rows.py.
- Fences and comments: lint/check_skill_model_rows.py live_lines is the one home for them. A fence left open before
  a role line exits 1, and the output names the fence and its line.

PROJECT_OPS_ROLES_CHECK is a red-run seam: it names a stand-in to run in place of the real check. The red run on the
base uses a stand-in that enforces nothing, so each case fails on its own assert ("expected exit N, got 0"), not on a
missing script. CI leaves it unset.

Each case names the defect it pins in its docstring. Red cases are marked "Red".
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECK = os.environ.get("PROJECT_OPS_ROLES_CHECK") or os.path.join(HERE, "check_project_ops_roles.py")
CHECKS = os.path.join(ROOT, ".github", "workflows", "checks.yml")
CHECK_STEP = "Project-ops roles check"
FIXTURE_STEP = "Project-ops roles fixture suite"

sys.path.insert(0, HERE)
from all_jobs_passed_rules import all_jobs  # noqa: E402  one home for the checks.yml step parser
from check_skill_model_rows import live_lines  # noqa: E402  one home for fences and multi-line HTML comments
import layout  # noqa: E402  one home of where records live (lint/layout.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

RUN_FOLDER = _test_temp.run_folder()
ROLES = ("coordinator", "triage", "batch runner", "lane", "arbiter", "consultant")
RECORD_NAME = "session-tiers.md"
RECORD = "decisions/" + RECORD_NAME  # the folder layout.path gives a fixture tree with no extras file (run() checks it)
TEMPLATES = "skills/project-ops/templates"
MODEL_NAME = "operating-model.md"
MODEL = TEMPLATES + "/" + MODEL_NAME
SENTENCE_START = "The session roles are the same on local and cloud: "
SENTENCE = SENTENCE_START + ("coordinator, triage, batch runner, lane, arbiter and consultant "
                             "(see the consultant sub-bullet below).")
SENTENCE_RE = re.compile(r"The session roles are the same on local and cloud: ([^.]*)\.")


def brief_name(role):
    """The template a role needs: lane has brief.md, every other role brief-<role>.md with hyphens."""
    return "brief.md" if role == "lane" else "brief-%s.md" % role.replace(" ", "-")


def brief_path(role):
    return TEMPLATES + "/" + brief_name(role)


def model_text(with_text=ROLES, before="", after=""):
    """operating-model.md with one role text line for each role in `with_text`, after `before` and before `after`."""
    lines = ["- **%s.** The %s session works its one line.\n" % (role.capitalize(), role) for role in with_text]
    return "# Operating model\n\n" + before + "".join(lines) + after


def record_text(sentence=SENTENCE, extra=""):
    """The record: some prose, the sentence when one is given, then `extra`."""
    head = "# Session tiers\n\nOwner rulings, one line each.\n\n"
    return head + ("%s\n" % sentence if sentence is not None else "") + extra


def clean():
    """The full tree: every role of SENTENCE has a role text and a non-empty brief template."""
    files = {RECORD: record_text(), MODEL: model_text(ROLES)}
    for role in ROLES:
        files[brief_path(role)] = "# Brief: %s\n\nThe brief body.\n" % role
    return files


def need_check():
    if not os.path.exists(CHECK):
        raise AssertionError("%s does not exist: no check reads the project-ops roles" % CHECK)


def run(files):
    """Build a fixture tree from {relpath: text} in this run's folder, run the check in it. -> (exit code, output lines)."""
    need_check()
    tree = tempfile.mkdtemp(prefix="ops_roles_", dir=RUN_FOLDER)
    try:
        tracked_tree.copy_tracked(tree, "lint")  # the check's imports and layout.json
        where = layout.path(tree, "decisions")
        if where != "decisions":
            raise AssertionError("fixture bug: layout puts the record in %r, not 'decisions'" % where)
        script = os.path.join(tree, "lint", "check_project_ops_roles.py")
        shutil.copy(CHECK, script)
        for rel, text in files.items():
            path = os.path.join(tree, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        proc = subprocess.run([sys.executable, script], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        return proc.returncode, (proc.stdout + proc.stderr).splitlines()
    finally:
        tracked_tree.rm_tree(tree)


def read_live(path):
    """The text of a repo file, outside fenced blocks and multi-line HTML comments."""
    with open(path, encoding="utf-8") as handle:
        return "\n".join(live_lines(handle.read()))


def session_roles(record):
    """The roles the sentence names, read as the check reads them. `record` is the live text of the record."""
    found = SENTENCE_RE.search(record)
    if not found:
        return []
    body = re.sub(r"\([^)]*\)", "", found.group(1))
    return [part.strip() for part in re.split(r",|\band\b", body) if part.strip()]


def role_text(model, role):
    """True when a live line of the model starts `- **<Role>.**`, any case."""
    return any(re.match(r"- \*\*%s\.\*\*" % re.escape(role), line, re.IGNORECASE) for line in model.splitlines())


class Fixture(unittest.TestCase):
    def check(self, files, code, lines=None, why=""):
        """Run `files`. Assert the exit code first (the scope), then the output lines when `lines` is given. -> output lines."""
        got, out = run(files)
        self.assertEqual(got, code, "%s: expected exit %d, got %d; output %r" % (why, code, got, out))
        if lines is not None:
            self.assertEqual(out, lines, "%s: output differs" % why)
        return out


class Clean(Fixture):
    def test_full_tree_exits_0_and_prints_nothing(self):
        # Green control: every role has its text and template, so the check passes and prints nothing.
        self.check(clean(), 0, [], "a complete tree must pass with no output")


class RoleText(Fixture):
    """Role text: one `- **Role.**` line per role, outside fences and comments, matched in any case."""

    def test_a_role_without_text_fails_alone(self):
        # Red: a role with no role text line fails, and no other role is named.
        for role in ROLES:
            with self.subTest(role=role):
                files = clean()
                files[MODEL] = model_text([r for r in ROLES if r != role])
                self.check(files, 1, ["role `%s`: no role text" % role],
                           "a role with no role text must fail, and only that role")

    def test_role_text_only_in_a_fence_does_not_count(self):
        # Red: arbiter's line sits in a fenced block only, so it is no role text.
        files = clean()
        files[MODEL] = model_text([r for r in ROLES if r != "arbiter"],
                                  after="```text\n- **Arbiter.** The arbiter session works its one line.\n```\n")
        self.check(files, 1, ["role `arbiter`: no role text"], "role text inside a fence must not count")

    def test_role_text_only_in_a_multi_line_comment_does_not_count(self):
        # Red: arbiter's line sits inside a multi-line HTML comment only, so it is no role text.
        files = clean()
        files[MODEL] = model_text([r for r in ROLES if r != "arbiter"],
                                  after="<!--\n- **Arbiter.** The arbiter session works its one line.\n-->\n")
        self.check(files, 1, ["role `arbiter`: no role text"], "role text inside a multi-line comment must not count")

    def test_a_role_named_in_prose_is_not_role_text(self):
        # Red: "The arbiter ..." in prose is not a `- **Arbiter.**` line.
        files = clean()
        files[MODEL] = model_text([r for r in ROLES if r != "arbiter"],
                                  after="The arbiter is a separate role that holds the ruling.\n")
        self.check(files, 1, ["role `arbiter`: no role text"], "a role named in prose must not count as role text")

    def test_role_text_matches_in_any_case(self):
        # Red: a lowercase `- **arbiter.**` line counts, so arbiter is not named. Partner: consultant has no
        # text at all, so consultant is named alone.
        files = clean()
        files[MODEL] = model_text([r for r in ROLES if r not in ("arbiter", "consultant")],
                                  after="- **arbiter.** The arbiter session works its one line.\n")
        self.check(files, 1, ["role `consultant`: no role text"],
                   "lowercase role text must count, and the missing consultant text must still fail")

    def test_scanner_markers_before_a_role_line_do_not_hide_it(self):
        # Red: "<!--" in a code span is plain text, and "Don't" is prose. The arbiter line after them still counts,
        # so only its missing template is named (rule building-scanner-respects-strings).
        files = clean()
        files[MODEL] = model_text(ROLES, before="Write `<!--` to open a comment, and say Don't.\n")
        del files[brief_path("arbiter")]
        self.check(files, 1, ["role `arbiter`: no brief template templates/brief-arbiter.md"],
                   "a code-span comment marker or an apostrophe in prose must not hide the role line after it")

    def test_a_bare_role_marker_is_not_role_text(self):
        # Control: a marker with words after it is role text, so the tree passes.
        # Red: a marker with nothing after it is no role text, so arbiter fails alone. The current pattern matches the
        # bare marker and exits 0.
        others = [r for r in ROLES if r != "arbiter"]
        files = clean()
        files[MODEL] = model_text(others, after="- **Arbiter.** Holds the ruling.\n")
        self.check(files, 0, [], "control: role text after the marker must count")
        for tail in ("", "   "):
            with self.subTest(tail=tail):
                files[MODEL] = model_text(others, after="- **Arbiter.**%s\n" % tail)
                self.check(files, 1, ["role `arbiter`: no role text"],
                           "a bare role marker must not count as role text")

    def test_an_unclosed_fence_before_a_role_line_is_named(self):
        # Control: a fence that closes before the role lines hides nothing, so the tree passes.
        # Red: the fence opened on line 3 never closes, so the role lines after it are hidden. The output must name
        # the fence, not only "no role text".
        files = clean()
        files[MODEL] = model_text(ROLES, before="```text\ncode\n```\n")
        self.check(files, 0, [], "control: a closed fence must hide nothing")
        files[MODEL] = model_text(ROLES, before="```text\n")
        out = self.check(files, 1, None, "an unclosed fence hides the role lines after it, so the run must exit 1")
        self.assertTrue(any("unclosed fence" in line and "line 3" in line for line in out),
                        "the output must name the unclosed fence on line 3: %r" % out)


class Templates(Fixture):
    """Brief templates: lane has brief.md, every other role brief-<role>.md, each non-empty."""

    def test_a_role_without_its_template_fails_alone(self):
        # Red: a role with no template fails, and only that role is named.
        for role in ROLES:
            with self.subTest(role=role):
                files = clean()
                del files[brief_path(role)]
                self.check(files, 1, ["role `%s`: no brief template templates/%s" % (role, brief_name(role))],
                           "a role with no brief template must fail, and only that role")

    def test_lane_reads_brief_md_and_not_brief_lane_md(self):
        # Red: lane's template is templates/brief.md. A brief-lane.md alone does not satisfy it.
        files = clean()
        del files[brief_path("lane")]
        files[TEMPLATES + "/brief-lane.md"] = "# Brief: lane\n"
        self.check(files, 1, ["role `lane`: no brief template templates/brief.md"],
                   "lane's brief template is brief.md, so brief-lane.md must not satisfy it")

    def test_an_empty_template_fails_its_role(self):
        # Red: an empty file is no brief. The brief gives no wording for it, so the case names the role and the path.
        for role in ("triage", "lane"):
            with self.subTest(role=role):
                files = clean()
                files[brief_path(role)] = ""
                out = self.check(files, 1, None, "an empty brief template must fail its role")
                self.assertEqual(len(out), 1, "an empty template must give one problem line: %r" % out)
                self.assertIn("`%s`" % role, out[0])
                self.assertIn("templates/%s" % brief_name(role), out[0])

    def test_a_one_word_template_is_not_empty(self):
        # Control: a template with one word has text, so it passes.
        files = clean()
        files[brief_path("triage")] = "Triage"
        self.check(files, 0, [], "a one-word template is fine")

    def test_a_blank_template_is_empty(self):
        # Red: a template of spaces, newlines or tabs has no text, so it fails as empty. The current check reads the
        # file size only, so it exits 0.
        for role in ("triage", "lane"):
            for blank in ("   ", "\n\n", " \t\r\n"):
                with self.subTest(role=role, blank=repr(blank)):
                    files = clean()
                    files[brief_path(role)] = blank
                    out = self.check(files, 1, None, "a blank brief template must fail as empty")
                    self.assertEqual(len(out), 1, "a blank template must give one problem line: %r" % out)
                    self.assertIn("`%s`" % role, out[0])
                    self.assertIn("templates/%s" % brief_name(role), out[0])
                    self.assertIn("empty", out[0])

    def test_a_template_for_a_role_the_sentence_does_not_name_is_fine(self):
        # Control: an unlisted builder template changes nothing. Red partner: it does not hide a missing triage template.
        files = clean()
        files[TEMPLATES + "/brief-builder.md"] = "# Brief: builder\n"
        self.check(files, 0, [], "a template for a role the sentence does not name must not fail the run")
        del files[brief_path("triage")]
        self.check(files, 1, ["role `triage`: no brief template templates/brief-triage.md"],
                   "an unlisted template must not hide a missing listed template")

    def test_a_batch_runner_template_is_named_with_hyphens(self):
        # Control: brief-batch-runner.md is the template. Red: a file named "brief-batch runner.md" (a space) is not.
        files = clean()
        self.check(files, 0, [], "brief-batch-runner.md must satisfy the batch runner role")
        del files[brief_path("batch runner")]
        files[TEMPLATES + "/brief-batch runner.md"] = "# Brief: batch runner\n"
        self.check(files, 1, ["role `batch runner`: no brief template templates/brief-batch-runner.md"],
                   "a space in a template name must not stand for a hyphen")

    def test_a_missing_templates_folder_exits_2_naming_it(self):
        # Red: no folder means no operating model and no templates: unreadable input, so exit 2.
        files = {name: text for name, text in clean().items() if not name.startswith(TEMPLATES + "/")}
        out = self.check(files, 2, None, "a missing templates folder is unreadable input")
        self.assertIn("templates", "\n".join(out), "the exit 2 output must name the templates folder: %r" % out)

    def test_a_missing_operating_model_exits_2_naming_it(self):
        # Red: role text cannot be read at all, so the run is unreadable input, exit 2.
        files = clean()
        del files[MODEL]
        out = self.check(files, 2, None, "a missing operating-model.md is unreadable input")
        self.assertIn(MODEL_NAME, "\n".join(out), "the exit 2 output must name operating-model.md: %r" % out)

    def test_an_empty_templates_folder_names_every_role(self):
        # Red: the empty state. Every role has text and none has a template, so there is one line per role.
        files = {RECORD: record_text(), MODEL: model_text(ROLES)}
        out = self.check(files, 1, None, "an empty templates folder must name every role")
        want = sorted("role `%s`: no brief template templates/%s" % (role, brief_name(role)) for role in ROLES)
        self.assertEqual(sorted(out), want, "one line per role with no template")


class Record(Fixture):
    """The session-roles sentence: read outside fences and comments, split as the check splits it."""

    def test_a_missing_record_exits_2_naming_it(self):
        # Red: no record means no roles. Exit 2 names the record.
        files = clean()
        del files[RECORD]
        out = self.check(files, 2, None, "a missing record is unreadable input")
        self.assertIn(RECORD_NAME, "\n".join(out), "the exit 2 output must name the record: %r" % out)

    def test_a_sentence_that_is_missing_or_hidden_exits_2(self):
        # Red: no sentence, a sentence only in a fence, and one only in a multi-line comment. None is read, so exit 2.
        cases = {
            "no sentence": record_text(sentence=None),
            "sentence only in a fence": record_text(sentence=None, extra="```text\n%s\n```\n" % SENTENCE),
            "sentence only in a comment": record_text(sentence=None, extra="<!--\n%s\n-->\n" % SENTENCE),
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                files = clean()
                files[RECORD] = text
                out = self.check(files, 2, None, "a sentence that is %s must fail closed" % label)
                self.assertIn(RECORD_NAME, "\n".join(out), "the exit 2 output must name the record: %r" % out)

    def test_a_sentence_that_gives_no_roles_exits_2(self):
        # Red: a sentence with only a parenthetical, or an empty list, gives no roles. Fails closed, never clean.
        cases = {
            "only a parenthetical": SENTENCE_START + "(see below).",
            "an empty list": SENTENCE_START + ".",
        }
        for label, sentence in cases.items():
            with self.subTest(case=label):
                files = clean()
                files[RECORD] = record_text(sentence)
                out = self.check(files, 2, None, "a sentence with %s gives no roles and must fail closed" % label)
                self.assertIn(RECORD_NAME, "\n".join(out), "the exit 2 output must name the record: %r" % out)

    def test_a_parenthetical_adds_no_roles(self):
        # Red: the parenthetical names triage, arbiter and batch runner, but they are not roles. Only consultant
        # lacks its template, so only consultant is named. A parse that keeps the parenthetical names more.
        files = clean()
        files[RECORD] = record_text(SENTENCE_START + "coordinator, lane (see triage, arbiter and batch runner) and consultant.")
        del files[brief_path("consultant")]
        self.check(files, 1, ["role `consultant`: no brief template templates/brief-consultant.md"],
                   "words in a parenthetical must not become roles")

    def test_a_final_and_splits_the_last_two_roles(self):
        # Control: "coordinator and consultant" passes with both templates. Red: a missing consultant template names
        # consultant alone, not "and consultant".
        files = clean()
        files[RECORD] = record_text(SENTENCE_START + "coordinator and consultant.")
        self.check(files, 0, [], "a final and must split two roles, and both are present")
        del files[brief_path("consultant")]
        self.check(files, 1, ["role `consultant`: no brief template templates/brief-consultant.md"],
                   "a final and must split off the last role, so the name is consultant alone")

    def test_a_role_the_sentence_does_not_name_needs_no_text_or_template(self):
        # Control: the sentence names coordinator and lane only, so arbiter and consultant need nothing. Red partner:
        # lane's brief.md is missing, so lane is named alone.
        files = clean()
        files[RECORD] = record_text(SENTENCE_START + "coordinator and lane.")
        files[MODEL] = model_text(["coordinator", "lane"])
        del files[brief_path("arbiter")]
        del files[brief_path("consultant")]
        self.check(files, 0, [], "roles the sentence does not name must need no text or template")
        del files[brief_path("lane")]
        self.check(files, 1, ["role `lane`: no brief template templates/brief.md"],
                   "a named role with no template must still fail")


    def test_a_period_inside_a_parenthetical_does_not_end_the_sentence(self):
        # Control: a parenthetical with no period passes. Red: the period in "2.1" must not end the sentence, so the
        # list is read whole. Mid-list, the role after the parenthetical must stay its own role.
        tail = "coordinator, triage, batch runner, lane, arbiter and consultant "
        with self.subTest(case="control: no period in the parenthetical"):
            files = clean()
            files[RECORD] = record_text(SENTENCE_START + tail + "(see section 2).")
            self.check(files, 0, [], "control: a parenthetical with no period must pass")
        with self.subTest(case="a period in the parenthetical"):
            files = clean()
            files[RECORD] = record_text(SENTENCE_START + tail + "(see section 2.1).")
            self.check(files, 0, [], "a period inside a parenthetical must not end the sentence")
        with self.subTest(case="a period in a mid-list parenthetical"):
            files = clean()
            files[RECORD] = record_text(SENTENCE_START + "coordinator, lane (see section 2.1) and consultant.")
            del files[brief_path("consultant")]
            self.check(files, 1, ["role `consultant`: no brief template templates/brief-consultant.md"],
                       "a period inside a mid-list parenthetical must keep consultant as its own role")

    def test_a_stray_period_in_the_role_list_exits_2(self):
        # Control: prose after the list's closing period, as the record has it, is not read as roles.
        # Red: "lane. Arbiter and consultant." ends a list that has commas and no final "and". The check must exit 2
        # and name the record, never drop roles silently.
        files = clean()
        files[RECORD] = record_text(SENTENCE + " Solo, one lane and lane session collapse into one role, lane.")
        self.check(files, 0, [], "control: prose after the closing period must not be read as roles")
        files[RECORD] = record_text(SENTENCE_START + "coordinator, triage, batch runner, lane. Arbiter and consultant.")
        out = self.check(files, 2, None, "a stray period that cuts the role list must fail closed")
        self.assertIn(RECORD_NAME, "\n".join(out), "the exit 2 output must name the record: %r" % out)

    def test_a_hard_wrapped_anchor_is_found(self):
        # Control: the anchor on one line passes. Red: a line break between words of the anchor, plain or at a
        # bullet's continuation indent, must still find the sentence.
        files = clean()
        self.check(files, 0, [], "control: the anchor on one line must pass")
        body = "coordinator, triage, batch runner, lane, arbiter and consultant (see the consultant sub-bullet below)."
        wraps = (
            ("plain wrap", "The session roles are the same on\nlocal and cloud: "),
            ("bullet continuation", "The session roles are the same on\n  local and cloud: "),
        )
        for label, anchor in wraps:
            with self.subTest(wrap=label):
                files[RECORD] = record_text(anchor + body)
                self.check(files, 0, [], "a hard-wrapped anchor (%s) must still be found" % label)

    def test_a_hyphen_in_the_sentence_names_the_spaced_role(self):
        # Control: "batch runner" in the sentence passes. Red: "batch-runner" must match the same text, "Batch runner",
        # and the same template, brief-batch-runner.md.
        files = clean()
        self.check(files, 0, [], "control: the spaced name must pass")
        files[RECORD] = record_text(SENTENCE_START + "coordinator, triage, batch-runner, lane, arbiter and consultant "
                                    "(see the consultant sub-bullet below).")
        self.check(files, 0, [], "a hyphen in the sentence must match role text Batch runner and brief-batch-runner.md")

    def test_a_space_in_the_sentence_names_the_hyphenated_role_text(self):
        # Control: "Batch runner" role text passes. Red: "batch runner" in the sentence must match hyphenated role
        # text, "- **Batch-runner.**".
        files = clean()
        self.check(files, 0, [], "control: spaced role text must pass")
        files[MODEL] = model_text([r for r in ROLES if r != "batch runner"],
                                  after="- **Batch-runner.** The batch runner session works its one line.\n")
        self.check(files, 0, [], "a space in the sentence must match hyphenated role text")


def sentence_with_capital(role):
    """The session-roles sentence with `role` capitalised, as a reader writes the list at its start."""
    names = [r.capitalize() if r == role else r for r in ROLES]
    return SENTENCE_START + ", ".join(names[:-1]) + " and %s (see the consultant sub-bullet below)." % names[-1]


class SentenceCase(Fixture):
    """A capitalised role in the sentence reads as its lowercase name: its template and its problem line use that name."""

    def test_a_capitalised_role_resolves_to_its_lowercase_template(self):
        # Control: the lowercase sentence passes on the full tree, so a failure below comes from the capital alone.
        # `Lane` is the role `lane`, and its template is brief.md, not brief-Lane.md.
        self.check(clean(), 0, [], "control: the lowercase sentence must pass on the full tree")
        for role in ROLES:
            with self.subTest(role=role):
                files = clean()
                files[RECORD] = record_text(sentence_with_capital(role))
                self.check(files, 0, [], "a capitalised %s must resolve to templates/%s, so the tree passes"
                           % (role, brief_name(role)))

    def test_a_missing_template_for_a_capitalised_role_is_named_in_lowercase(self):
        # Control: with the lowercase sentence, the problem line names the role and its template in lowercase.
        # The capitalised sentence must print the same line. Otherwise the reader is pointed at a file name that
        # the templates folder does not use.
        for role in ROLES:
            expected = ["role `%s`: no brief template templates/%s" % (role, brief_name(role))]
            files = clean()
            del files[brief_path(role)]
            with self.subTest(role=role, sentence="lowercase"):
                self.check(files, 1, expected, "control: the lowercase sentence must name the missing template in lowercase")
            files[RECORD] = record_text(sentence_with_capital(role))
            with self.subTest(role=role, sentence="capitalised"):
                self.check(files, 1, expected, "the problem line for a capitalised %s must name it in lowercase" % role)


class CiWiring(unittest.TestCase):
    def step(self, name):
        with open(CHECKS, encoding="utf-8") as handle:
            jobs = all_jobs(handle.read())
        self.assertIn("checks", jobs, "checks.yml has no checks job")
        found = [s for s in jobs["checks"]["steps"] if s.get("name") == name]
        self.assertEqual(len(found), 1, "checks job needs exactly one step named %r" % name)
        return found[0]

    def test_checks_job_runs_the_check(self):
        # Pins one checks-job step that runs the check. An if: condition could skip it and read as passing.
        step = self.step(CHECK_STEP)
        self.assertEqual(step.get("run"), "python3 lint/check_project_ops_roles.py")
        self.assertNotIn("if", step, "an if: condition lets a skipped check read as passing")

    def test_checks_job_runs_the_fixture_suite(self):
        # Pins one checks-job step that runs this suite. An if: condition could skip it and read as passing.
        step = self.step(FIXTURE_STEP)
        self.assertEqual(step.get("run"), "python3 lint/test_check_project_ops_roles.py")
        self.assertNotIn("if", step, "an if: condition lets a skipped suite read as passing")


class RealRepo(Fixture):
    def test_real_repo_has_text_and_a_template_for_each_role_and_passes_the_check(self):
        # Pins that each role the session roles sentence names has role text and a brief template. A gap is its own
        # subtest, so it names its role and cause. The check runs last.
        record = read_live(os.path.join(ROOT, *layout.path(ROOT, "decisions").split("/"), RECORD_NAME))
        roles = session_roles(record)
        self.assertTrue(roles, "the session roles sentence names no roles in %s" % RECORD_NAME)
        model = read_live(os.path.join(ROOT, *MODEL.split("/")))
        for role in roles:
            with self.subTest(role=role):
                self.assertTrue(role_text(model, role), "role `%s`: no role text in %s" % (role, MODEL))
        for role in roles:
            with self.subTest(role=role):
                path = os.path.join(ROOT, *TEMPLATES.split("/"), brief_name(role))
                self.assertTrue(os.path.isfile(path),
                                "role `%s`: no brief template templates/%s" % (role, brief_name(role)))
                self.assertGreater(os.path.getsize(path), 0,
                                   "role `%s`: brief template templates/%s is empty" % (role, brief_name(role)))
        need_check()
        proc = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(proc.returncode, 0, "the check on this repo exits non-zero: %s" % (proc.stdout + proc.stderr))
        self.assertEqual(proc.stdout + proc.stderr, "", "the check on this repo prints a problem line")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
