#!/usr/bin/env python3
"""Fixture suite for lint/check_agent_models.py. Run: python3 lint/test_check_agent_models.py

Haiku is allowed only in the agent files for Explore, claude-code-guide, test-author and reviewer.
Every other agent or skill file keeps the Sonnet floor.
Failure classes: false deny (a listed role fails), false allow (another file passes, by name
collision, case or alias), unreadable frontmatter.
One case reads the real agents/plan.md: its "Premises first" paragraph cites the premise record.
The lane session row of docs/decisions/agent-model-cap.md must start its effort cell with medium.
A drift between the guard's role lists and the role table fails the check (the guard's role_list_drift).
An agent file's `model:` pin must equal its role's row in the role table. The role is the frontmatter `name:`,
as the guard keys it. A file with no pin, or a name with no row, is not flagged by that rule.
Every agent file that can run Bash names TaskStop in its body, and its tools: allowlist lists it (debt
agent-reports-with-live-watcher). The test reads each agents/*.md file, not a list of names.
An agent body must not state the agent's own model in fixed text: a sentence with `your ... model` and a model name
in it, or a backticked PASS/FAIL/PARTIAL header that names a model. A body whose report header has a model slot
(`the model` or `<model>`) must also name the line that gives the model: `powered by the model named`. Each failure
names its file and line as file:line.
Every agent file withholds the claude-code-remote server: disallowedTools: names the whole server (`mcp__claude-code-remote__*`
or bare `mcp__claude-code-remote`), or tools: is an allow-list with no entry for it. Only the frontmatter counts, never the
body or a description.
"""
import contextlib, io, os, re, shutil, sys, tempfile, time, unittest, uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import check_agent_models as C  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "hooks"))
from tool_lists_test import tokens, unread_list  # noqa: E402  the one reader of tool lists (hooks/tool_lists_test.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()

ROLES = ("explore", "claude-code-guide", "test-author", "reviewer")
MODELS = ("haiku", "claude-haiku-5-5", "Haiku")
# The model table of docs/decisions/agent-model-cap.md, reduced to its lane session row. Only the effort cell varies.
RECORD_RELPATH = os.path.join("docs", "decisions", "agent-model-cap.md")
LANE_RECORD = ("| Point | Model | Effort |\n|---|---|---|\n"
               "| lane session (decision `session-tiers`) | sonnet (temporary), the owner's ruling of 2026-11-08 12:21 CST, waiting-page item 439 (lane-model-sonnet), pick none; debt `lane-model-recheck` rechecks it | %s |\n")


def verdict(relpath, model=None, closed=True, text=None, relative=False, name="x", pinned=True):
    """Write one fixture under this run's folder and return the check's (code, stdout).

    An agent file with frontmatter, unless `text` gives the whole file (a record). `relative` runs
    the check from the fixture's folder with the path as given, as a run from a repository root does.
    `name` is the frontmatter name, the role key. `pinned=False` writes no model line.
    """
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as tmp:
        path = os.path.join(tmp, relpath)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as handle:
            if text is None:
                head = "---\nname: %s\ndisallowedTools: mcp__claude-code-remote__*\n%s" % (
                    name, "model: %s\n" % model if pinned else "")
                handle.write("%s%sbody\n" % (head, "---\n" if closed else ""))
            else:
                handle.write(text)
        out = io.StringIO()
        before = os.getcwd()
        if relative:
            os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(out):
                code = C.main([relpath if relative else path])
        finally:
            os.chdir(before)
        return code, out.getvalue()


class Haiku(unittest.TestCase):
    def test_listed_roles_may_set_haiku(self):
        for role in ROLES:
            for model in MODELS:
                with self.subTest(role=role, model=model):
                    self.assertEqual(verdict("agents/%s.md" % role, model), (0, ""))

    def test_other_agents_still_fail(self):
        for name in ("builder", "plan", "general-purpose", "claude", "reviewer-lite", "explorer"):
            with self.subTest(name=name):
                self.assertEqual(verdict("agents/%s.md" % name, "haiku")[0], 1)

    def test_skill_files_still_fail(self):
        # A skill named like a role is still a skill.
        for name in ("deploy", "explore", "reviewer", "test-author"):
            with self.subTest(name=name):
                self.assertEqual(verdict("skills/%s/SKILL.md" % name, "haiku")[0], 1)

    def test_listed_roles_may_set_sonnet(self):
        for role in ROLES:
            self.assertEqual(verdict("agents/%s.md" % role, "sonnet"), (0, ""))

    def test_unclosed_frontmatter_still_fails_for_a_listed_role(self):
        self.assertEqual(verdict("agents/reviewer.md", "haiku", closed=False)[0], 1)


def names(out, filename, *words):
    """True when one line of the check's output names the file and each word."""
    return any(filename in line and all(word in line for word in words) for line in out.splitlines())


class PinEqualsRow(unittest.TestCase):
    # The role is the frontmatter `name:`, as the guard keys it (role_agent_keys). Table keys are case-exact (Explore,
    # Plan). The rows come from the real record through the guard's one reader. A case that names a row first asserts
    # that row, so a moved row reads as a stale case, not as a false pass.
    def assertRow(self, role, row):
        table = C._guard.role_model_table(C.ROOT) or {}
        self.assertEqual(table.get(role), row, "the record's row for %r moved; re-point the cases that name it" % role)

    def agent(self, role, model):
        return verdict("agents/%s.md" % role.lower(), model, name=role)

    def test_pin_that_differs_from_its_row_is_flagged(self):
        # Sonnet and opus pins clear the Haiku floor, so these fail only on the pin-equals-row rule.
        cases = (("reviewer", "sonnet", "haiku"), ("reviewer", "claude-sonnet-5-5", "haiku"),
                 ("reviewer", "opus", "haiku"), ("Explore", "sonnet", "haiku"),
                 ("Plan", "sonnet", "opus"), ("designer", "sonnet", "opus"), ("design-reviewer", "sonnet", "opus"))
        for role, pin, row in cases:
            with self.subTest(role=role, pin=pin):
                self.assertRow(role, row)
                code, out = self.agent(role, pin)
                self.assertEqual(code, 1, "pin %s on the %s row passes: %r" % (pin, row, out))
                self.assertTrue(names(out, "%s.md" % role.lower(), pin, row),
                                "no line names the file, the pin and the row: %r" % out)

    def test_pin_equal_to_its_row_passes(self):
        cases = [("Plan", "opus", "opus"), ("Plan", "claude-opus-5-5", "opus"), ("designer", "opus", "opus"),
                 ("design-reviewer", "opus", "opus"), ("builder", "sonnet", "sonnet")]
        cases += [(role, model, "haiku") for role in ("Explore", "claude-code-guide", "test-author", "reviewer",
                                                       "record-writer") for model in MODELS]
        for role, model, row in cases:
            with self.subTest(role=role, model=model):
                self.assertRow(role, row)
                self.assertEqual(self.agent(role, model), (0, ""))

    def test_file_with_no_model_pin_is_not_flagged(self):
        for role in ("builder", "reviewer"):
            with self.subTest(role=role):
                self.assertRow(role, "sonnet" if role == "builder" else "haiku")
                self.assertEqual(verdict("agents/%s.md" % role, name=role, pinned=False), (0, ""))

    def test_role_with_no_table_row_is_not_flagged(self):
        self.assertNotIn("some-role", C._guard.role_model_table(C.ROOT) or {})
        self.assertEqual(verdict("agents/some-role.md", "sonnet", name="some-role"), (0, ""))
        self.assertEqual(verdict("agents/some-role.md", "opus", name="some-role"), (0, ""))

    def test_pin_is_read_past_comments_quotes_and_indented_text(self):
        # Source-text cases (building-scanner-respects-strings): a comment that names the other model, a lone quote in
        # another key's text, and an indented `model:` line inside a block scalar. Only the top-level pin counts.
        self.assertRow("reviewer", "haiku")
        flagged = (("comment names the row word", "model: sonnet  # not haiku\n"),
                   ("lone quote in another key", "description: Don't pin it\nmodel: sonnet\n"),
                   ("indented model line in a block scalar",
                    "description: |\n  model: haiku\n  it's a note\nmodel: sonnet\n"))
        for label, lines in flagged:
            with self.subTest(label):
                code, out = verdict("agents/reviewer.md", text="---\nname: reviewer\n%s---\nbody\n" % lines)
                self.assertEqual(code, 1, "%s: a sonnet pin on the haiku row passes: %r" % (label, out))
                self.assertTrue(names(out, "reviewer.md", "sonnet", "haiku"),
                                "%s: no line names the pin and the row: %r" % (label, out))
        # A comment after a haiku pin that names sonnet leaves the pin haiku, so the file passes.
        self.assertEqual(verdict("agents/reviewer.md",
                                 text="---\nname: reviewer\ndisallowedTools: mcp__claude-code-remote__*\n"
                                      "model: haiku  # sonnet is above the row\n---\nbody\n"),
                         (0, ""))


# The kind is the backticked first cell of a table row, as hooks/test_precompact_handoff.py reads it.
KIND_ROW = re.compile(r"^\|\s*`([a-z]+)`\s*\|", re.M)


class PlanPremises(unittest.TestCase):
    def test_premises_first_cites_the_record_and_copies_no_kind(self):
        with open(os.path.join(ROOT, "agents", "plan.md"), encoding="utf-8") as handle:
            paragraphs = re.split(r"\n\s*\n", handle.read())
        found = [p for p in paragraphs if p.startswith("Premises first")]
        self.assertEqual(len(found), 1, "agents/plan.md needs one 'Premises first' paragraph")
        self.assertIn("`premise-format`", found[0])
        # One home for the kinds: docs/decisions/premise-format.md. The plan agent points at it.
        with open(os.path.join(ROOT, "docs", "decisions", "premise-format.md"), encoding="utf-8") as handle:
            kinds = KIND_ROW.findall(handle.read())
        self.assertTrue(kinds, "no kind rows in docs/decisions/premise-format.md")
        for kind in kinds:
            with self.subTest(kind=kind):
                self.assertIsNone(re.search(r"\b%s\b" % kind, found[0], re.I),
                                  "the paragraph copies the kind %r; cite the record" % kind)


class LaneEffort(unittest.TestCase):
    # The check reads the record it is given as a path. A record at docs/decisions/agent-model-cap.md fails
    # unless the lane session row's effort cell starts with the lane effort, medium.
    def record(self, effort):
        return verdict(RECORD_RELPATH, text=LANE_RECORD % effort)

    def test_lane_row_effort_default_fails(self):
        code, out = self.record("default")
        self.assertEqual(code, 1, "a lane row at effort default passes: %r" % out)

    def test_lane_row_effort_starting_medium_passes(self):
        self.assertEqual(self.record("medium, the owner's ruling of 2026-10-30 15:11 CDT"), (0, ""))

    def test_lane_row_effort_must_start_with_medium(self):
        # A medium later in the cell is not the lane effort: the cell must start with it.
        code, out = self.record("default, medium")
        self.assertEqual(code, 1, "a lane row whose cell only mentions medium passes: %r" % out)

    def test_relative_record_path_with_default_row_fails(self):
        # The check must read the record when the path is relative, as a run from the repository root gives it.
        code, out = verdict(RECORD_RELPATH, text=LANE_RECORD % "default", relative=True)
        self.assertEqual(code, 1, "a relative record path with a default lane row passes: %r" % out)


class RoleListDrift(unittest.TestCase):
    # The check fails when the guard's role_list_drift names drift, and passes when it names none. The check looks
    # the function up at run time, so the patch takes effect (decision agent-model-cap, the three role lists).
    def run_main(self, lines):
        """Run the check on this repository with role_list_drift patched to `lines`: (code, stdout, pointers)."""
        pointers = []

        def fake(pointer_root):
            pointers.append(pointer_root)
            return list(lines)

        out = io.StringIO()
        with mock.patch.object(C._guard, "role_list_drift", fake, create=True), contextlib.redirect_stdout(out):
            code = C.main([])
        return code, out.getvalue(), pointers

    def test_drift_fails_the_check_and_prints_the_line(self):
        line = "test-author is on a sonnet row but in HAIKU_ROLES (hooks/guard.py)"
        code, out, pointers = self.run_main([line])
        self.assertEqual(code, 1, "a drift line from role_list_drift passes the check: %r" % out)
        self.assertIn(line, out)
        self.assertEqual(pointers, [C.ROOT], "the check does not call role_list_drift on this repository")

    def test_no_drift_passes_the_check(self):
        code, out, _ = self.run_main([])
        self.assertEqual((code, out), (0, ""), "no drift from role_list_drift still fails the check: %r" % out)


class RoundRowDrift(unittest.TestCase):
    """The record's round rows and review rows are read by the guard and the merge tool (one home, decision agent-model-cap). A row
    the guard cannot read is drift: the check fails and names that row. A readable row passes, and so does the real record
    (test_main_with_no_args_passes_on_the_real_repo)."""
    ROLE_ROWS = "| Point | Model | Effort |\n|---|---|---|\n| reviewer | haiku | xhigh |\n| builder | sonnet | high |\n"
    ROUND_HEAD = "| Role | Round | Model | Effort |\n|---|---|---|---|\n"
    POLICY_HEAD = ("| Kind | Guard or check | Rounds owed after a pass | Last round | Net value owed after a failed last round |\n"
                   "|---|---|---|---|---|\n")
    POLICY_ROW_OK = "| normal | no | 1 | 3 | no |"  # one well-formed review row; the merge suite's fixture states all six

    def write_fixture(self, round_row, round_table=True, policy_row=POLICY_ROW_OK):
        """A pointer folder whose record holds the role rows, the round table with `round_row` (or no round table when
        `round_table` is false), the lane row, and the review rows table with `policy_row` (none when it is None). Returns the folder's root."""
        root = tempfile.mkdtemp(dir=RUN_FOLDER)
        os.makedirs(os.path.join(root, "agents"))
        record = os.path.join(root, RECORD_RELPATH)
        os.makedirs(os.path.dirname(record))
        rounds = self.ROUND_HEAD + round_row + "\n" if round_table else ""
        policy = "\n" + self.POLICY_HEAD + policy_row + "\n" if policy_row else ""
        with open(record, "w", encoding="utf-8") as handle:
            handle.write(self.ROLE_ROWS + "\n" + rounds + LANE_RECORD % "medium" + policy)
        return root

    def check_fixture(self, round_row, round_table=True, policy_row=POLICY_ROW_OK):
        """The check run over write_fixture's folder: (code, stdout). The role lists are patched out, so only the round rows
        and the review rows can fail the check."""
        root = self.write_fixture(round_row, round_table, policy_row)
        out = io.StringIO()
        with mock.patch.object(C, "ROOT", root), contextlib.redirect_stdout(out), \
                mock.patch.object(C._guard, "role_list_drift", lambda pointer_root: [], create=True):
            code = C.main([])
        return code, out.getvalue()

    def assert_scope(self, root, rounds):
        """Scope before verdict: the fixture holds the role table, and the guard reads its round table exactly when `rounds`."""
        self.assertIsNotNone(C._guard.role_model_table(root), "the fixture holds no role table, so this case proves nothing")
        self.assertEqual(C._guard.role_round_table(root) is not None, rounds,
                         "the guard's round table read for this fixture is not %s, so this case proves nothing" % rounds)

    def test_a_round_row_naming_a_model_the_guard_cannot_read_fails_the_check(self):
        code, out = self.check_fixture("| reviewer | 2 | fable | high |")
        self.assertEqual(code, 1, "a round row naming a model the guard cannot read passes the check: %r" % out)
        self.assertTrue(names(out, "agent-model-cap.md", "fable"), "the check does not name the round row it flags: %r" % out)

    def test_a_round_row_the_guard_reads_passes_the_check(self):
        code, out = self.check_fixture("| reviewer | 2 | sonnet | high |")
        self.assertEqual((code, out), (0, ""), "a readable round row fails the check: %r" % out)

    def test_a_record_with_no_round_rows_table_fails_the_check(self):
        # The record keeps its role table and lane row, and has no round table. The guard reads no round row from it, so the
        # check must fail it, not pass it silently.
        self.assert_scope(self.write_fixture("", round_table=False), rounds=False)
        code, out = self.check_fixture("", round_table=False)
        self.assertEqual(code, 1, "a record with no round rows table passes the check: %r" % out)
        self.assertIn("agent-model-cap.md", out, "the check does not name the record it flags: %r" % out)

    def test_a_round_table_with_no_rows_fails_the_check(self):
        # The empty state of the round table: its header and separator, and no row. The guard reads no round row from it.
        self.assert_scope(self.write_fixture(""), rounds=False)
        code, out = self.check_fixture("")
        self.assertEqual(code, 1, "a round table with no rows passes the check: %r" % out)
        self.assertIn("agent-model-cap.md", out, "the check does not name the record it flags: %r" % out)

    def test_the_real_record_round_table_holds_the_round_one_other_row(self):
        # Control: the guard reads the real record's round table, with the reviewer's first-round other row, so the real repo's pass is a read.
        self.assertIn(("reviewer", "1", "other"), C._guard.role_round_table(C.ROOT) or {})

    def assert_policy_row_fails(self, policy_row, cause):
        """The check fails the record whose review rows table holds `policy_row`, and names that row."""
        code, out = self.check_fixture("| reviewer | 2 | sonnet | high |", policy_row=policy_row)
        self.assertEqual(code, 1, "a review row with %s passes the check: %r" % (cause, out))
        self.assertTrue(names(out, "agent-model-cap.md", policy_row), "the check does not name the review row it flags: %r" % out)

    def test_a_review_row_with_a_kind_outside_the_review_kinds_fails_the_check(self):
        self.assert_policy_row_fails("| normal-change | no | 1 | 3 | no |", "a kind outside the review kinds")

    def test_a_review_row_with_a_guard_word_other_than_yes_or_no_fails_the_check(self):
        self.assert_policy_row_fails("| normal | maybe | 1 | 3 | no |", "a Guard or check word other than yes or no")

    def test_a_review_row_with_a_round_cell_that_is_not_a_number_fails_the_check(self):
        self.assert_policy_row_fails("| normal | no | two | 3 | no |", "a round cell that is not a number")

    def test_a_review_row_with_a_last_round_above_the_cap_fails_the_check(self):
        self.assert_policy_row_fails("| normal | no | 1 | 4 | no |", "a last round above three")

    def test_a_well_formed_review_row_passes_and_the_round_and_role_readers_read_the_record_as_before(self):
        # Control: the review rows table changes neither reader, so the readers agree with and without it.
        with_table = self.write_fixture("| reviewer | 2 | sonnet | high |")
        without = self.write_fixture("| reviewer | 2 | sonnet | high |", policy_row=None)
        self.assertEqual(C._guard.role_round_table(with_table), C._guard.role_round_table(without), "the review rows table changes the round rows")
        self.assertEqual(C._guard.role_model_table(with_table), C._guard.role_model_table(without), "the review rows table changes the role rows")
        self.assertEqual(self.check_fixture("| reviewer | 2 | sonnet | high |"), (0, ""), "a well-formed review row fails the check")


class RunFolder(unittest.TestCase):
    def test_first_request_sweeps_old_siblings_and_keeps_new_ones(self):
        # test-temp-standard: the first request of a run removes a sibling over a day old and keeps a newer one.
        root = os.path.join(RUN_FOLDER, "sweep")
        old = os.path.join(root, "1-%s" % uuid.uuid4().hex)
        new = os.path.join(root, "2-%s" % uuid.uuid4().hex)
        for path in (old, new):
            os.makedirs(path)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(temp_root=root)
        self.assertFalse(os.path.exists(old), "an old sibling run folder survived the sweep")
        self.assertTrue(os.path.isdir(new), "a new sibling run folder was swept")
        self.assertTrue(os.path.isdir(own))


def agent_parts(text):
    """(keys, body, problem) of one agent file: the frontmatter keys, the text after the frontmatter, and the problem
    when no closed frontmatter block opens the file. Keys come from the guard's one reader of agent frontmatter."""
    head = C.frontmatter(text)
    if head is None:
        return None, None, "frontmatter never closes"
    if not head:
        return None, None, "no frontmatter block"
    return C._guard.frontmatter_keys(head), "\n".join(text.splitlines()[len(head) + 2:]), None


def runs_bash(keys):
    """True when the frontmatter lets the agent run Bash: `tools:` is absent or lists Bash (`Bash` or `Bash(...)`),
    and `disallowedTools:` does not name Bash."""
    allowed = tokens(keys["tools"]) if "tools" in keys else None
    denied = tokens(keys.get("disallowedTools", ""))
    listed = allowed is None or any(item == "Bash" or item.startswith("Bash(") for item in allowed)
    return listed and "Bash" not in denied


class TaskStopLine(unittest.TestCase):
    # Debt agent-reports-with-live-watcher. An agent that can run Bash can start a background task, so its file tells it
    # to stop its tasks with TaskStop first. A tools: allowlist without TaskStop would leave the agent unable to follow that.
    def agent_texts(self):
        folder = os.path.join(ROOT, "agents")
        names = sorted(name for name in os.listdir(folder) if name.endswith(".md"))
        self.assertTrue(names, "agents/ holds no agent file to read")
        texts = []
        for name in names:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                texts.append((name, handle.read()))
        return texts

    def test_bash_capable_agent_names_taskstop_in_its_body(self):
        for name, text in self.agent_texts():
            with self.subTest(agent=name):
                keys, body, problem = agent_parts(text)
                self.assertIsNone(problem, "%s: %s" % (name, problem))
                field = unread_list(keys)
                self.assertIsNone(field, "%s: the %s list sits below its key, which this check does not read" % (name, field))
                if runs_bash(keys):
                    self.assertTrue("TaskStop" in body, "%s can run Bash, but its body never names TaskStop" % name)

    def test_bash_capable_agent_with_a_tools_allowlist_lists_taskstop(self):
        for name, text in self.agent_texts():
            with self.subTest(agent=name):
                keys, _, problem = agent_parts(text)
                self.assertIsNone(problem, "%s: %s" % (name, problem))
                field = unread_list(keys)
                self.assertIsNone(field, "%s: the %s list sits below its key, which this check does not read" % (name, field))
                if "tools" in keys and runs_bash(keys):
                    self.assertTrue("TaskStop" in tokens(keys["tools"]),
                                    "%s can run Bash and has a tools: allowlist with no TaskStop, so it cannot follow the stop line" % name)


# The self-model rules read an agent file's body. The fixtures are agents/fixture.md with a name and no model pin, so
# the pin and floor rules stay quiet and only the body rules can fail.
PHRASE_LINE = "You are powered by the model named in your system prompt."
SLOT = "Under Done, the first line is `PASS, round 1 of 3, <model>`."
BARE_SLOT = "Under Done, the first line is PASS, FAIL, or PARTIAL, then the round and the model."


def agent_text(body, description=None):
    """A fixture agent file: a frontmatter block with a name, an optional description, then the body."""
    keys = ["name: fixture", "disallowedTools: mcp__claude-code-remote__*"] + (
        ["description: %s" % description] if description else [])
    return "---\n%s\n---\n%s" % ("\n".join(keys), body)


def line_of(text, needle):
    """The 1-based numbers of the file lines that hold `needle`."""
    return [number for number, line in enumerate(text.splitlines(), 1) if needle in line]


def names_line(out, basename, numbers):
    """True when one line of the check's output names the file and one of the numbers as file:line."""
    wanted = ["%s:%d" % (basename, number) for number in numbers]
    return any(re.search(re.escape(name) + r"(?!\d)", line) for line in out.splitlines() for name in wanted)


class OwnModelInBody(unittest.TestCase):
    def check(self, body):
        return verdict("agents/fixture.md", text=agent_text(body))

    def assertFlagged(self, body, needle):
        """The body fails, and the failure names the file and the one line that holds `needle`."""
        text = agent_text(body)
        numbers = line_of(text, needle)
        self.assertEqual(len(numbers), 1, "fixture error: %r is not on exactly one line" % needle)
        code, out = verdict("agents/fixture.md", text=text)
        self.assertEqual(code, 1, "a body that states the agent's own model passes the check: %r" % needle)
        self.assertTrue(names_line(out, "fixture.md", numbers),
                        "the failure does not name fixture.md:%d: %r" % (numbers[0], out))

    def test_sentence_naming_the_agents_own_model_is_flagged(self):
        for sentence in ("Round 1 runs on your frontmatter model, haiku.", "Your model is sonnet for this round.",
                         "You run on your model: opus."):
            with self.subTest(sentence=sentence):
                self.assertFlagged("Intro.\n\n%s\n" % sentence, sentence)

    def test_own_model_sentence_wrapped_over_two_lines_is_flagged(self):
        text = agent_text("Round 1 runs on your frontmatter\nmodel, haiku.\n")
        first = line_of(text, "your frontmatter")
        self.assertEqual(len(first), 1, "fixture error: the wrap moved off one line")
        code, out = verdict("agents/fixture.md", text=text)
        self.assertEqual(code, 1, "a wrapped sentence that states the agent's own model passes the check")
        self.assertTrue(names_line(out, "fixture.md", [first[0], first[0] + 1]),
                        "the failure does not name the sentence's lines as fixture.md:N: %r" % out)

    def test_report_header_naming_a_model_is_flagged(self):
        for header in ("`PASS, fix check, haiku`", "`FAIL, round 2 of 3, sonnet`", "`PARTIAL, round 1 of 3, Opus`"):
            with self.subTest(header=header):
                self.assertFlagged("Under Done, the first line is %s.\n" % header, header)

    def test_report_header_wrapped_onto_its_model_is_flagged(self):
        # The header span crosses a line break before its model word, so a match on one line misses it.
        for header, start in (("`FAIL, round 2 of 3,\nhaiku`", "FAIL, round 2 of 3,"),
                              ("`PASS, fix check,\nsonnet`", "PASS, fix check,")):
            with self.subTest(header=header):
                text = agent_text("Under Done, the first line is %s.\n" % header)
                first = line_of(text, start)
                self.assertEqual(len(first), 1, "fixture error: the header start is not on one line")
                code, out = verdict("agents/fixture.md", text=text)
                self.assertEqual(code, 1, "a header wrapped onto its model passes the check: %r" % header)
                self.assertTrue(names_line(out, "fixture.md", [first[0], first[0] + 1]),
                                "the failure does not name fixture.md:%d for the header: %r" % (first[0], out))

    def test_defect_after_a_comment_opener_or_a_stray_quote_is_flagged(self):
        cases = (("It's the first round. Round 1 runs on your frontmatter model, haiku.\n", "your frontmatter model"),
                 ("Use `//` and `#` in prose. Round 1 runs on your frontmatter model, haiku.\n",
                  "your frontmatter model"),
                 ("A stray ` mark opens no code span. Under Done, the first line is `PASS, fix check, haiku`.\n",
                  "`PASS, fix check, haiku`"),
                 ("# Notes // the lone \" quote stays. Your model is sonnet.\n", "Your model is sonnet"))
        for body, needle in cases:
            with self.subTest(needle=needle):
                self.assertFlagged(body, needle)

    def test_defect_on_the_last_line_of_a_long_body_is_flagged(self):
        filler = "".join("Filler line %d.\n" % number for number in range(2000))
        self.assertFlagged(filler + "Round 1 runs on your frontmatter model, haiku.\n", "your frontmatter model")

    def test_other_roles_model_prose_is_not_flagged(self):
        body = ("The orchestrator spawns rounds 2 and 3 on Sonnet, the ceiling.\n"
                "Set `model: haiku` in the frontmatter.\n")
        self.assertEqual(self.check(body), (0, ""), "prose about another role's model is flagged")

    def test_own_model_and_a_model_name_in_separate_sentences_are_not_flagged(self):
        body = "Your report names the model it used. Sonnet is the ceiling for the orchestrator.\n"
        self.assertEqual(self.check(body), (0, ""), "a model name in the next sentence is flagged with the one before")

    def test_empty_body_is_not_flagged(self):
        self.assertEqual(self.check(""), (0, ""), "an agent file with no body is flagged")


class ModelSlot(unittest.TestCase):
    def check(self, body, description=None):
        return verdict("agents/fixture.md", text=agent_text(body, description))

    def test_model_slot_header_without_the_phrase_is_flagged(self):
        for line in (SLOT, BARE_SLOT):
            with self.subTest(line=line):
                text = agent_text(line + "\n")
                numbers = line_of(text, line)
                self.assertEqual(len(numbers), 1, "fixture error: the header is not on one line")
                code, out = verdict("agents/fixture.md", text=text)
                self.assertEqual(code, 1, "a model-slot header passes with no `powered by the model named` line")
                self.assertTrue(names_line(out, "fixture.md", numbers),
                                "the failure does not name fixture.md:%d: %r" % (numbers[0], out))

    def test_phrase_in_the_frontmatter_does_not_count(self):
        text = agent_text(SLOT + "\n", description=PHRASE_LINE)
        numbers = line_of(text, SLOT)
        self.assertEqual(len(numbers), 1, "fixture error: the header is not on one line")
        code, out = verdict("agents/fixture.md", text=text)
        self.assertEqual(code, 1, "the phrase in the frontmatter satisfies the body rule")
        self.assertTrue(names_line(out, "fixture.md", numbers),
                        "the failure does not name fixture.md:%d: %r" % (numbers[0], out))

    def test_model_slot_header_with_the_phrase_in_the_body_passes(self):
        self.assertEqual(self.check(PHRASE_LINE + "\n\n" + SLOT + "\n"), (0, ""),
                         "a <model> placeholder header with the phrase in the body is flagged")
        self.assertEqual(self.check(PHRASE_LINE + "\n\n" + BARE_SLOT + "\n"), (0, ""),
                         "a `the model` header with the phrase in the body is flagged")

    def test_header_without_a_model_slot_needs_no_phrase(self):
        self.assertEqual(self.check("Under Done, the first line is `PASS, fix check`.\n"), (0, ""),
                         "a header with no model slot is flagged for the missing phrase")

    def test_phrase_wrapped_over_a_line_break_still_counts(self):
        # A line break inside the phrase is a space in the prose, so the wrapped phrase is in the body.
        for wrapped in ("You are powered by the model\nnamed in your system prompt.",
                        "You are powered by\nthe model named in your system prompt."):
            with self.subTest(wrapped=wrapped):
                self.assertEqual(self.check(wrapped + "\n\n" + SLOT + "\n"), (0, ""),
                                 "a model-slot header is flagged for a phrase that wraps across a line break")


class RealAgentFiles(unittest.TestCase):
    # Each real agent file is checked alone, so a finding fails only that file's subtest, and the subtest names it.
    def test_every_real_agent_file_passes_the_check(self):
        folder = os.path.join(ROOT, "agents")
        names = sorted(name for name in os.listdir(folder) if name.endswith(".md"))
        self.assertTrue(names, "agents/ holds no agent file to check")
        for name in names:
            with self.subTest(agent=name):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = C.main([os.path.join(folder, name)])
                self.assertEqual(code, 0, "agents/%s fails the check: %r" % (name, out.getvalue()))
                self.assertEqual(out.getvalue(), "", "agents/%s exits 0 but prints a finding" % name)


REMOTE = "mcp__claude-code-remote"


def agent_with(*lines, body="body\n"):
    """A fixture agent file, agents/fixture.md: a frontmatter block with a name and the given lines, then the body."""
    return "---\n%s\n---\n%s" % ("\n".join(("name: fixture",) + lines), body)


def server_withheld(keys):
    """True when the agent cannot reach the claude-code-remote server: disallowedTools: names the whole server, or tools:
    is an allow-list with no entry for it. It reads the files, not the check, so the repo case is red before the check
    is built."""
    denied = tokens(keys.get("disallowedTools", ""))
    if REMOTE in denied or REMOTE + "__*" in denied:
        return True
    if "tools" in keys:
        return not any(item == REMOTE or item.startswith(REMOTE + "__") for item in tokens(keys["tools"]))
    return False


class SessionTools(unittest.TestCase):
    # Every agent file withholds the claude-code-remote server, since an agent that reaches it can create or message
    # sessions it was not briefed on. Only the frontmatter counts. The cases go through main(), so a red case fails on
    # its exit-code assert, not on a missing name.
    def scope(self, text, absent=(), present=()):
        """The fixture's frontmatter has the keys the case means, so the verdict reads the key it tests."""
        keys, _, problem = agent_parts(text)
        self.assertIsNone(problem, "fixture error: %s" % problem)
        for key in absent:
            self.assertNotIn(key, keys, "fixture error: the frontmatter has a %s: key" % key)
        for key in present:
            self.assertIn(key, keys, "fixture error: the frontmatter has no %s: key" % key)

    def red(self, text, what):
        code, out = verdict("agents/fixture.md", text=text)
        self.assertEqual(code, 1, "%s passes the check: %r" % (what, out))
        self.assertTrue(names(out, "fixture.md"), "no line names fixture.md for %s: %r" % (what, out))

    def clean(self, text, what):
        code, out = verdict("agents/fixture.md", text=text)
        self.assertEqual((code, out), (0, ""), "%s is flagged: %r" % (what, out))

    def test_agent_with_no_tools_or_refuse_key_is_flagged(self):
        text = agent_with()
        self.scope(text, absent=("tools", "disallowedTools"))
        self.red(text, "an agent with no tools: and no disallowedTools: key")

    def test_refuse_list_without_the_server_is_flagged(self):
        self.red(agent_with("disallowedTools: Edit, Write, NotebookEdit"), "a deny list with no remote entry")

    def test_empty_refuse_list_is_flagged(self):
        self.red(agent_with("disallowedTools:"), "an empty disallowedTools: that withholds nothing")

    def test_refuse_of_one_remote_tool_is_flagged(self):
        # The server is withheld whole. A deny of one remote tool leaves the other remote tools reachable.
        self.red(agent_with("disallowedTools: Edit, Write, mcp__claude-code-remote__create_session"),
                 "a deny of one remote tool, not the server")

    def test_refuse_of_another_server_is_flagged(self):
        self.red(agent_with("disallowedTools: Edit, Write, mcp__claude-code-remoteX__*"),
                 "a deny of another server, named by a prefix")

    def test_allow_list_naming_a_remote_tool_is_flagged(self):
        self.red(agent_with("tools: Bash, Read, mcp__claude-code-remote__create_session"),
                 "a tools: allow-list that names a remote tool")

    def test_allow_list_in_yaml_form_naming_a_remote_tool_is_flagged(self):
        self.red(agent_with("tools: [Bash, Read, mcp__claude-code-remote__create_session]"),
                 "a YAML-list tools: that names a remote tool")

    def test_allow_list_naming_the_whole_server_is_flagged(self):
        self.red(agent_with("tools: mcp__claude-code-remote__*"), "a tools: allow-list that names the whole server")

    def test_allow_list_naming_the_bare_server_is_flagged(self):
        self.red(agent_with("tools: Bash, mcp__claude-code-remote"), "a tools: allow-list that names the bare server")

    def test_refuse_only_in_the_body_is_flagged(self):
        text = agent_with(body="disallowedTools: mcp__claude-code-remote__*\n")
        self.scope(text, absent=("tools", "disallowedTools"))
        self.red(text, "a deny written in the body, not the frontmatter")

    def test_refuse_only_in_the_description_is_flagged(self):
        text = agent_with('description: "Withheld with disallowedTools: mcp__claude-code-remote__* in its file."')
        self.scope(text, absent=("tools", "disallowedTools"), present=("description",))
        self.red(text, "a deny written in the description, not as a frontmatter key")

    def test_refuse_written_as_an_indented_block_line_is_flagged(self):
        text = agent_with("description: |", "  disallowedTools: mcp__claude-code-remote__*")
        self.scope(text, absent=("tools", "disallowedTools"))
        self.red(text, "a deny indented under a block scalar, so it is not a key")

    def test_lone_quote_in_another_key_does_not_hide_a_remote_tool(self):
        text = agent_with("description: Don't use // or # here.",
                          "tools: Bash, mcp__claude-code-remote__create_session")
        self.scope(text, absent=("disallowedTools",), present=("tools",))
        self.red(text, "a remote tool after a description with a lone quote and comment openers")

    def test_refuse_of_the_whole_server_passes(self):
        self.clean(agent_with("disallowedTools: Edit, Write, NotebookEdit, mcp__claude-code-remote__*"),
                   "a deny that names the whole server")

    def test_refuse_of_the_bare_server_passes(self):
        self.clean(agent_with("disallowedTools: Edit, Write, mcp__claude-code-remote"),
                   "a deny that names the bare server")

    def test_yaml_list_refuse_passes(self):
        self.clean(agent_with("disallowedTools: [Edit, mcp__claude-code-remote__*]"), "a YAML-list deny of the server")

    def test_refuse_with_a_trailing_comment_passes(self):
        self.clean(agent_with("disallowedTools: Edit, Write, mcp__claude-code-remote__*  # the server is never needed"),
                   "a deny of the server with a trailing comment")

    def test_full_size_refuse_list_passes(self):
        refuse = ", ".join(["Edit", "Write", "NotebookEdit", "Bash", "Read", "Glob", "Grep", "WebFetch", "WebSearch",
                         "Task", "TodoWrite", "mcp__claude-code-remote__*"])
        self.clean(agent_with("disallowedTools: %s" % refuse), "a full-size deny list that ends in the server")

    def test_allow_list_without_a_remote_entry_passes(self):
        self.clean(agent_with("tools: Bash, Read, WebFetch, WebSearch, TaskStop"),
                   "a tools: allow-list with no remote entry")

    def test_allow_list_naming_another_server_passes(self):
        self.clean(agent_with("tools: Bash, Read, mcp__claude-code-remoteX__ping"),
                   "a tools: allow-list that names another server")

    def test_lone_quote_in_another_key_does_not_hide_a_refuse(self):
        self.clean(agent_with("description: Don't use // or # here.", "disallowedTools: Edit, mcp__claude-code-remote__*"),
                   "a deny after a description with a lone quote and comment openers")


class SessionToolsRepo(unittest.TestCase):
    def test_main_with_no_args_passes_on_the_real_repo(self):
        # A control: it passes on the old code, where the check is not built yet. It guards the real agent files once it is.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = C.main([])
        self.assertEqual((code, out.getvalue()), (0, ""), "main() with no args flags the real repo: %r" % out.getvalue())

    def test_every_real_agent_file_withholds_the_remote_server(self):
        folder = os.path.join(ROOT, "agents")
        files = sorted(name for name in os.listdir(folder) if name.endswith(".md"))
        self.assertTrue(files, "agents/ holds no agent file to read")
        for name in files:
            with self.subTest(agent=name):
                with open(os.path.join(folder, name), encoding="utf-8-sig") as handle:
                    keys, _, problem = agent_parts(handle.read())
                self.assertIsNone(problem, "%s: %s" % (name, problem))
                field = unread_list(keys)
                self.assertIsNone(field, "%s: the %s list sits below its key, which this check does not read" % (name, field))
                self.assertTrue(server_withheld(keys),
                                "agents/%s can reach the claude-code-remote server: disallowedTools: names no remote "
                                "entry, and it has no tools: allow-list" % name)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
