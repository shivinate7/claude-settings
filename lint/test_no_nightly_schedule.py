#!/usr/bin/env python3
"""Cases for the daily schedule: .github/workflows/checks.yml runs on push to main, on pull_request, on workflow_dispatch,
and on one daily schedule. Standard library only.

    python3 lint/test_no_nightly_schedule.py

The daily schedule replaces the no-nightly drop (owner page item 880, 11:53 CST Nov 15). It is the one run that
runs the Windows, mutation and other slow legs a push no longer runs. The schedule is one `cron:` line, under
`schedule:` and nowhere else, daily, at a minute that is not 0.

The on: block is read by its text, from the top-level `on:` line to the next top-level key, because no YAML library
is on a fresh runner. A trigger is a key, or a list item, at the block's own indent. A comment is cut before the read,
and a block scalar's body is skipped, so a schedule word in a comment, a string or a job's if: is no trigger.
CHECKS_YML overrides the checks.yml path, for a scratch copy.

PushGroup reads the top-level concurrency: block the same way and evaluates its group for a push run and a pull request run, so
a newer push run of main replaces a pending one (see the comment above PushGroup).
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CHECKS = os.environ.get("CHECKS_YML") or os.path.join(REPO, ".github", "workflows", "checks.yml")

ON = re.compile(r"on\s*:")  # matched from column 0, so only a top-level key matches
KEY = re.compile(r"([A-Za-z_][\w-]*)\s*:(?:\s|$)")
ITEM = re.compile(r"-\s*([A-Za-z_][\w-]*)\s*$")
CRON = re.compile(r"(?:-\s+)?cron\s*:")
BLOCK_SCALAR = re.compile(r":\s*[|>][-+0-9]*$")
JOBS = "jobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"


def strip_comment(line):
    """The line without its YAML comment. A `#` opens one at column 0 or after a space, outside a quoted value. A quote
    opens a value only where one starts (after `:`, `-`, `[` or `,`), so the apostrophe in `Don't` is text."""
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if quote == '"' and c == "\\":
                i += 2
                continue
            if c == quote:
                if quote == "'" and line[i + 1:i + 2] == "'":
                    i += 2
                    continue
                quote = None
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
        elif c in "'\"" and line[:i].rstrip()[-1:] in (":", "-", "[", ","):
            quote = c
        i += 1
    return line.rstrip()


def read_on(text):
    """The top-level on: block of a workflow, or None when the file has no on: key. -> (triggers, lines).
    triggers is [(name, line number)]: the keys or list items at the block's own indent, or the items of an inline
    value (`on: [push, schedule]`). lines is [(line number, text)] for each meaningful line of the block, comments cut
    and block-scalar bodies left out."""
    raw_lines = text.splitlines()
    start = next((n for n, raw in enumerate(raw_lines) if ON.match(raw)), None)
    if start is None:
        return None
    head = strip_comment(raw_lines[start])[ON.match(raw_lines[start]).end():].strip()
    triggers, lines = [], []
    if head:
        items = head.strip("[]").split(",") if head.startswith("[") else [head]
        triggers = [(item.strip().strip("'\""), start + 1) for item in items if item.strip()]
        lines.append((start + 1, head))
    block = []
    body_indent = None
    for n in range(start + 1, len(raw_lines)):
        raw = raw_lines[n]
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if body_indent is not None and indent > body_indent:
            continue
        body_indent = None
        if indent == 0 and not raw.startswith("#"):
            break
        content = strip_comment(raw).strip()
        if not content:
            continue
        block.append((n + 1, indent, content))
        if BLOCK_SCALAR.search(content):
            body_indent = indent
    if block:
        own = min(indent for _, indent, _ in block)
        for line, indent, content in block:
            found = (KEY.match(content) or ITEM.match(content)) if indent == own else None
            if found:
                triggers.append((found.group(1), line))
    lines.extend((line, content) for line, _, content in block)
    return triggers, lines


def checks_text():
    with open(CHECKS, encoding="utf-8") as handle:
        return handle.read()


def cron_value(content):
    """The expression of a `cron:` line, quotes removed, or None when the line is no cron line."""
    m = re.match(r"(?:-\s+)?cron\s*:\s*(.*?)\s*$", content)
    if m is None:
        return None
    value = m.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def daily_problems(on):
    """Each reason the on: block's schedule is not one daily cron off the hour: exactly one cron line, five fields, a minute from 1 to 59,
    an hour from 0 to 23, and the last three fields `*` (every day of the month, month and weekday)."""
    crons = [(line, cron_value(text)) for line, text in on[1] if CRON.match(text)]
    if len(crons) != 1:
        return [f"the on: block has {len(crons)} cron lines, want one"]
    line, value = crons[0]
    fields = (value or "").split()
    if len(fields) != 5:
        return [f"line {line}: cron {value!r} has {len(fields)} fields, want 5"]
    minute, hour, dom, month, dow = fields
    problems = []
    if not (minute.isdigit() and 1 <= int(minute) <= 59):
        problems.append(f"line {line}: cron minute {minute!r} is not 1 to 59: a cron on the hour is not the daily run item 880 asks for")
    if not (hour.isdigit() and int(hour) <= 23):
        problems.append(f"line {line}: cron hour {hour!r} is not 0 to 23")
    if (dom, month, dow) != ("*", "*", "*"):
        problems.append(f"line {line}: cron {value!r} is not daily: its last three fields must be *")
    return problems


def cron_owner_problems(on):
    """Each cron line that sits under a trigger other than `schedule`: the one owner of a cron is the schedule key above it."""
    triggers = on[0]
    problems = []
    for line, text in on[1]:
        if not CRON.match(text):
            continue
        owners = [name for name, at in triggers if at < line]
        owner = owners[-1] if owners else None
        if owner != "schedule":
            problems.append(f"the cron at line {line} sits under {owner!r}, want schedule")
    return problems


def workflow(on_block, jobs=JOBS):
    return "name: checks\n" + on_block + jobs


class OnBlockCase(unittest.TestCase):
    def on_block(self, text):
        on = read_on(text)
        self.assertIsNotNone(on, "fixture has no top-level on: block")  # scope before the subject
        return on

    def names(self, on):
        return [name for name, _ in on[0]]


class ChecksYmlTriggers(unittest.TestCase):
    def setUp(self):
        self.on = read_on(checks_text())

    # Re-pointed (owner page item 880, 11:53 CST Nov 15): the daily schedule replaces the no-nightly ruling (22:19 CST Nov 12).
    # Named failure on the old file: no schedule trigger, so the Windows, mutation and other slow legs never run on main.
    def test_on_block_has_one_schedule_trigger(self):
        self.assertIsNotNone(self.on, "checks.yml has no top-level on: block")
        hits = [line for name, line in self.on[0] if name == "schedule"]
        self.assertEqual(len(hits), 1, f"checks.yml on: block lists the schedule trigger {len(hits)} times, want one daily schedule")

    def test_on_block_has_one_cron_line(self):
        self.assertIsNotNone(self.on, "checks.yml has no top-level on: block")
        hits = [line for line, text in self.on[1] if CRON.match(text)]
        self.assertEqual(len(hits), 1, f"checks.yml on: block has {len(hits)} cron lines, want one")

    def test_the_cron_is_daily_and_off_the_hour(self):
        self.assertIsNotNone(self.on, "checks.yml has no top-level on: block")
        self.assertEqual(daily_problems(self.on), [], "the daily schedule's cron is not one daily cron off the hour")

    def test_the_cron_sits_under_schedule_and_never_under_push_or_pull_request(self):
        self.assertIsNotNone(self.on, "checks.yml has no top-level on: block")
        self.assertTrue(any(CRON.match(text) for _, text in self.on[1]), "checks.yml on: block has no cron line to read its owner")
        self.assertEqual(cron_owner_problems(self.on), [], "a cron sits under a trigger other than schedule")

    def test_on_block_keeps_workflow_dispatch(self):
        self.assertIsNotNone(self.on, "checks.yml has no top-level on: block")
        names = [name for name, _ in self.on[0]]
        self.assertIn("workflow_dispatch", names, "checks.yml on: block lost the workflow_dispatch trigger")

    def test_on_block_keeps_push_and_pull_request(self):
        self.assertIsNotNone(self.on, "checks.yml has no top-level on: block")
        names = [name for name, _ in self.on[0]]
        for trigger in ("push", "pull_request"):
            with self.subTest(trigger=trigger):
                self.assertIn(trigger, names, f"checks.yml on: block lost the {trigger} trigger")


class ReadsTheOnBlock(OnBlockCase):
    SCHEDULE = workflow('on:\n  push:\n  schedule:\n    - cron: "0 6 * * *"\n')

    def test_a_schedule_key_at_the_block_indent_is_a_trigger(self):
        # Positive control: the reader sees a real schedule, so the negative cases below prove something.
        self.assertIn("schedule", self.names(self.on_block(self.SCHEDULE)), "reader misses a schedule key at the block's indent")

    def test_a_cron_under_a_schedule_is_a_cron_line(self):
        on = self.on_block(self.SCHEDULE)
        self.assertTrue(any(CRON.match(text) for _, text in on[1]), "reader misses the cron line under schedule")

    def test_a_daily_cron_off_the_hour_under_schedule_has_no_problem(self):
        # Green control for the daily checks above: the reader and both checkers accept the shape item 880 asks for.
        on = self.on_block(workflow('on:\n  push:\n  schedule:\n    - cron: "47 8 * * *"\n'))
        self.assertEqual(daily_problems(on), [], "a daily cron off the hour is refused")
        self.assertEqual(cron_owner_problems(on), [], "a cron under schedule is refused")

    def test_a_cron_on_the_hour_is_refused(self):
        on = self.on_block(workflow('on:\n  push:\n  schedule:\n    - cron: "0 6 * * *"\n'))
        self.assertTrue(daily_problems(on), "a cron at minute 0 is accepted as the daily schedule")

    def test_a_weekly_cron_is_refused(self):
        on = self.on_block(workflow('on:\n  push:\n  schedule:\n    - cron: "47 8 * * 1"\n'))
        self.assertTrue(daily_problems(on), "a cron that runs on one weekday is accepted as the daily schedule")

    def test_a_cron_under_push_is_refused(self):
        on = self.on_block(workflow('on:\n  push:\n    - cron: "47 8 * * *"\n  schedule:\n'))
        self.assertTrue(cron_owner_problems(on), "a cron under push is accepted")

    def test_a_schedule_in_a_comment_is_no_trigger(self):
        on = self.on_block(workflow("on:\n  # schedule: nightly, dropped\n  push:  # schedule: none\n"
                                    "  # - cron: \"0 6 * * *\"\n  workflow_dispatch:\n"))
        self.assertEqual(self.names(on), ["push", "workflow_dispatch"], "reader reads a schedule word in a comment as a trigger")
        self.assertFalse(any(CRON.match(text) for _, text in on[1]), "reader reads a cron in a comment as a cron line")

    def test_a_schedule_in_a_job_if_is_outside_the_on_block(self):
        on = self.on_block(workflow("on:\n  push:\n  workflow_dispatch:\n",
                                    jobs="jobs:\n  nightly:\n    if: github.event_name == 'schedule'\n    runs-on: ubuntu-latest\n"))
        self.assertEqual(self.names(on), ["push", "workflow_dispatch"], "reader reads a job's if: as a trigger")

    def test_a_schedule_word_in_a_quoted_value_is_no_trigger(self):
        on = self.on_block(workflow('on:\n  workflow_dispatch:\n    inputs:\n      note:\n'
                                    '        description: "Runs on schedule: never on a push"\n  push:\n'))
        self.assertEqual(self.names(on), ["workflow_dispatch", "push"], "reader reads a schedule word in a quoted value as a trigger")

    def test_a_hash_inside_quotes_is_text_not_a_comment(self):
        on = self.on_block(workflow('on:\n  workflow_dispatch:\n    inputs:\n      note:\n'
                                    '        description: "a # schedule: x"\n  push:\n'))
        self.assertEqual(self.names(on), ["workflow_dispatch", "push"], "reader cuts a quoted value at its # and loses the keys")

    def test_a_lone_apostrophe_does_not_swallow_the_keys_after_it(self):
        on = self.on_block(workflow("on:\n  workflow_dispatch:\n    inputs:\n      note:\n"
                                    "        description: Don't run on schedule # schedule: none\n  push:\n"))
        self.assertEqual(self.names(on), ["workflow_dispatch", "push"], "reader loses the keys after a lone apostrophe")

    def test_a_block_scalar_body_is_no_trigger_and_no_cron(self):
        on = self.on_block(workflow("on:\n  push:\n  workflow_dispatch:\n    inputs:\n      note:\n        description: >\n"
                                    "          Runs nightly.\n          schedule:\n          - cron: daily\n        type: boolean\n"))
        self.assertEqual(self.names(on), ["push", "workflow_dispatch"], "reader reads a block scalar's body as a trigger")
        self.assertFalse(any(CRON.match(text) for _, text in on[1]), "reader reads a block scalar's body as a cron line")

    def test_an_inline_list_names_its_triggers_and_drops_its_comment(self):
        on = self.on_block(workflow("on: [push, pull_request, workflow_dispatch] # schedule removed\n"))
        self.assertEqual(self.names(on), ["push", "pull_request", "workflow_dispatch"], "reader misses an item of an inline on: list")

    def test_an_inline_list_with_schedule_names_schedule(self):
        on = self.on_block(workflow("on: [push, schedule]\n"))
        self.assertIn("schedule", self.names(on), "reader misses schedule in an inline on: list")

    def test_an_empty_on_block_names_no_trigger(self):
        on = self.on_block(workflow("on:\n"))
        self.assertEqual(self.names(on), [], "reader names a trigger in an empty on: block")

    def test_a_file_with_no_on_key_has_no_on_block(self):
        self.assertIsNone(read_on("name: checks\n" + JOBS), "reader finds an on: block in a file with none")

    def test_a_full_size_on_block_reads_every_trigger(self):
        notes = "".join(f"  # note {i}: schedule was dropped\n" for i in range(200))
        on = self.on_block(workflow("on:\n" + notes + "  push:\n    branches: [main]\n  pull_request:\n"
                                    "    types: [opened, synchronize]\n  workflow_dispatch:\n    inputs:\n      full:\n"
                                    "        description: Run.\n        type: boolean\n"))
        self.assertEqual(self.names(on), ["push", "pull_request", "workflow_dispatch"], "reader loses a trigger in a long on: block")


# PushGroup: the top-level concurrency: block of checks.yml, read by its text and evaluated for one push run and one pull request run. GitHub
# keeps one pending run per group and replaces it with the newer one, so a replaced pending run starts no job (the mechanism pinned here).
# The expression reader covers the operators checks.yml uses: string literals, context names, ==, !=, &&, ||, format() and parentheses.
TOKEN = re.compile(r"'[^']*'|==|!=|&&|\|\||[(),]|[A-Za-z_][\w.\-]*|\d+|\s+")


def concurrency_block(text):
    """The lines of the top-level concurrency: block: from its key to the next top-level key. Blank and comment lines are skipped."""
    out, inside = [], False
    for line in text.splitlines():
        if not inside:
            inside = line.rstrip() == "concurrency:"
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break
        out.append(line)
    return out


def block_value(block, key):
    """The raw value of a two-space child key of a block, or None when the block has no such key."""
    for line in block:
        m = re.match(r"  " + re.escape(key) + r":[ \t]?(.*)$", line)
        if m:
            return m.group(1).strip()
    return None


def tokens(text):
    out, pos = [], 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if m is None:
            raise ValueError("cannot read the expression at %d: %r" % (pos, text))
        if not m.group().isspace():
            out.append(m.group())
        pos = m.end()
    return out


class Expression:
    """A recursive-descent reader of one ${{ }} expression. Precedence as GitHub's: ==, then &&, then ||, and a value is the value of
    the operand that decides it (`a || b` is a when a is truthy, else b)."""
    def __init__(self, text, ctx):
        self.toks, self.ctx, self.at = tokens(text), ctx, 0

    def peek(self):
        return self.toks[self.at] if self.at < len(self.toks) else None

    def take(self):
        tok = self.peek()
        self.at += 1
        return tok

    def expect(self, want):
        if self.take() != want:
            raise ValueError("expected %r in the expression" % want)

    def value(self):
        v = self.or_()
        if self.peek() is not None:
            raise ValueError("unread tokens after the expression: %r" % self.toks[self.at:])
        return v

    def or_(self):
        v = self.and_()
        while self.peek() == "||":
            self.take()
            w = self.and_()
            v = v or w
        return v

    def and_(self):
        v = self.eq()
        while self.peek() == "&&":
            self.take()
            w = self.eq()
            v = v and w
        return v

    def eq(self):
        v = self.atom()
        if self.peek() in ("==", "!="):
            op = self.take()
            w = self.atom()
            v = (v == w) if op == "==" else (v != w)
        return v

    def atom(self):
        tok = self.take()
        if tok is None:
            raise ValueError("the expression ends early")
        if tok.startswith("'"):
            return tok[1:-1]
        if tok == "(":
            v = self.or_()
            self.expect(")")
            return v
        if tok == "format":
            self.expect("(")
            args = [self.or_()]
            while self.peek() == ",":
                self.take()
                args.append(self.or_())
            self.expect(")")
            return args[0].format(*args[1:])
        if tok in ("true", "false"):
            return tok == "true"
        if tok in self.ctx:
            return self.ctx[tok]
        raise ValueError("no such context %r" % tok)


def render(raw, ctx):
    """The string a value like `${{ a }}-${{ b }}` gives: each expression's value, a bool as true or false, null as empty."""
    out = []
    for i, part in enumerate(re.split(r"\$\{\{(.*?)\}\}", raw)):
        if i % 2 == 0:
            out.append(part)
            continue
        v = Expression(part, ctx).value()
        out.append("true" if v is True else "false" if v is False else "" if v is None else str(v))
    return "".join(out)


def run_context(event, run_id, ref, draft=None):
    """The github context of one run, the keys checks.yml reads. A push run has no pull request, so its draft is null."""
    return {"github.workflow": "checks", "github.event_name": event, "github.ref": ref, "github.run_id": str(run_id),
            "github.event.pull_request.draft": draft}


class ExpressionReader(unittest.TestCase):
    def test_a_string_compare_and_a_bool_render_as_github_writes_them(self):
        self.assertEqual(render("${{ github.event_name == 'push' }}-${{ false }}", run_context("push", 1, "refs/heads/main")), "true-false")

    def test_or_takes_the_decided_operand_and_format_fills_its_braces(self):
        ctx = run_context("pull_request", 7, "refs/pull/7/merge", False)
        self.assertEqual(render("${{ github.event_name == 'pull_request' && format('{0}-{1}', github.ref, github.event.pull_request.draft) || github.run_id }}", ctx),
                         "refs/pull/7/merge-False")
        self.assertEqual(render("${{ github.event_name == 'pull_request' && format('{0}', github.ref) || github.run_id }}", run_context("push", 7, "refs/heads/main")),
                         "7")


class PushGroup(unittest.TestCase):
    """checks.yml's top-level concurrency: group and cancel-in-progress, evaluated for a push run and a pull request run."""
    def setUp(self):
        self.block = concurrency_block(checks_text())
        self.group = block_value(self.block, "group")
        self.cancel = block_value(self.block, "cancel-in-progress")
        self.assertIsNotNone(self.group, "checks.yml's top-level concurrency: block has no group key")
        self.assertIsNotNone(self.cancel, "checks.yml's top-level concurrency: block has no cancel-in-progress key")

    def test_two_push_runs_of_main_share_one_group(self):
        """Red on origin/main: each push run has a group of its own (the run id), so a newer push run never replaces a pending one."""
        first = render(self.group, run_context("push", 101, "refs/heads/main"))
        second = render(self.group, run_context("push", 102, "refs/heads/main"))
        self.assertEqual(first, second, "two push runs of main are in different groups, so a newer push run never replaces a pending one")

    def test_control_two_pull_request_runs_of_one_ref_share_one_group(self):
        """Control, green on origin/main: pull request runs of one ref and draft state still share a group, so a new push cancels the old run."""
        first = render(self.group, run_context("pull_request", 201, "refs/pull/7/merge", False))
        second = render(self.group, run_context("pull_request", 202, "refs/pull/7/merge", False))
        self.assertEqual(first, second, "two pull request runs of one ref are in different groups")

    def test_control_a_push_run_never_cancels_the_run_in_progress(self):
        """Control, green on origin/main: a push run keeps cancel-in-progress false, so a running job is never cancelled."""
        self.assertEqual(render(self.cancel, run_context("push", 101, "refs/heads/main")), "false", "a push run cancels the run in progress")

    def test_control_a_pull_request_run_cancels_the_older_run_of_its_ref(self):
        """Control, green on origin/main: pull request runs keep cancel-in-progress true."""
        self.assertEqual(render(self.cancel, run_context("pull_request", 201, "refs/pull/7/merge", False)), "true",
                         "a pull request run does not cancel the older run in progress")


if __name__ == "__main__":
    unittest.main()
