#!/usr/bin/env python3
"""The review rows: which rounds a change owes, read from the model record (decision agent-model-cap, "The review rows").

merge.review_state reads a change's row, by its kind and Guard or check, through hooks/guard.py's pointer checkout, the way
review_round_model reads the round rows. A changed row changes the verdict with no code edit. Each case points the guard's
pointer checkout at a temp checkout whose record it names, and first proves that the round-row reader reads that checkout
(scope before verdict). Run: python3 merge/test_review_policy.py
"""
import contextlib, os, sys, tempfile, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_merge as tm  # noqa: E402  the review record's one home: record_text, record_verdict, fix_state, REVIEW_FIX_PASS
import merge  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(HERE), "hooks"))  # append: no hook module shadows one this suite imports
import guard as hook_guard  # noqa: E402  the pointer checkout and the round rows (hooks/guard.py)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import layout  # noqa: E402  where each kind of record lives (lint/layout.py)

REPO = tm.REPO_ROOT
RECORD_FOLDER = layout.layout()["kinds"]["decisions"]["path"].strip("/").split("/")
RECORD_NAME = hook_guard.ROLE_TABLE_FILE
ROUND_HEADER = "| Role | Round | Model | Effort |"
ROUND_TWO_ROW = "| reviewer | 2 | sonnet | high |"
ROUND_TWO_MARK = "| reviewer | 2 | haiku | high |"  # the shipped record names sonnet, so a read that gives haiku came from the temp checkout
POLICY_HEADER = "| Kind | Guard or check | Rounds owed after a pass | Last round | Net value owed after a failed last round |"
POLICY_SEPARATOR = "|---|---|---|---|---|"
COLUMN = {"owed": 2, "last": 3, "net": 4}  # the index of each cell of a review row
# The shipped review rows: kind, Guard or check, rounds owed after a pass, last round, net value owed after a failed last round.
SHIPPED_ROWS = (
    ("normal", "no", "1", "3", "no"),
    ("normal", "yes", "1", "3", "yes"),
    ("delete-only", "no", "1", "1", "no"),
    ("delete-only", "yes", "1", "3", "yes"),
    ("docs-only", "no", "0", "3", "no"),
    ("docs-only", "yes", "0", "3", "yes"),
)
# (kind, Guard or check, rounds as P and F letters, fix check as P, F or None, net value, the state the policy gives).
MATRIX = (
    ("normal", "no", "", None, "not owed", "open"),
    ("normal", "no", "P", None, "not owed", "done"),
    ("normal", "no", "F", None, "not owed", "open"),
    ("normal", "no", "FP", None, "not owed", "done"),
    ("normal", "no", "FF", None, "not owed", "open"),
    ("normal", "no", "FFP", None, "not owed", "done"),
    ("normal", "no", "FFF", None, "not owed", "done"),
    ("normal", "no", "FFF", None, "negative", "held"),
    ("normal", "no", "F", "P", "not owed", "done"),
    ("normal", "no", "FF", "F", "not owed", "open"),
    ("normal", "yes", "", None, "not owed", "open"),
    ("normal", "yes", "P", None, "not owed", "done"),
    ("normal", "yes", "F", None, "not owed", "open"),
    ("normal", "yes", "FP", None, "not owed", "done"),
    ("normal", "yes", "FF", None, "not owed", "open"),
    ("normal", "yes", "FFP", None, "not owed", "done"),
    ("normal", "yes", "FFF", None, "not owed", "open"),
    ("normal", "yes", "FFF", None, "zero", "done"),
    ("normal", "yes", "FFF", None, "positive", "done"),
    ("normal", "yes", "FFF", None, "negative", "held"),
    ("normal", "yes", "F", "P", "not owed", "done"),
    ("normal", "yes", "FFF", "P", "not owed", "done"),
    ("delete-only", "no", "", None, "not owed", "open"),
    ("delete-only", "no", "P", None, "not owed", "done"),
    ("delete-only", "no", "F", None, "not owed", "done"),
    ("delete-only", "yes", "", None, "not owed", "open"),
    ("delete-only", "yes", "P", None, "not owed", "done"),
    ("delete-only", "yes", "F", None, "not owed", "open"),
    ("delete-only", "yes", "FP", None, "not owed", "done"),
    ("delete-only", "yes", "FF", None, "not owed", "open"),
    ("delete-only", "yes", "FFP", None, "not owed", "done"),
    ("delete-only", "yes", "FFF", None, "not owed", "open"),
    ("delete-only", "yes", "FFF", None, "zero", "done"),
    ("docs-only", "no", "", None, "not owed", "done"),
    ("docs-only", "no", "P", None, "not owed", "done"),
    ("docs-only", "no", "F", None, "not owed", "open"),
    ("docs-only", "no", "FFF", None, "not owed", "done"),
    ("docs-only", "yes", "", None, "not owed", "done"),
    ("docs-only", "yes", "F", None, "not owed", "open"),
    ("docs-only", "yes", "FFF", None, "not owed", "open"),
    ("docs-only", "yes", "FFF", None, "zero", "done"),
)
# The normal, no rows of MATRIX: the controls a missing or unreadable row must still give (the old code gives the same for them).
NORMAL_NO = tuple(row for row in MATRIX if row[:2] == ("normal", "no"))


def round_lines(letters):
    """The round lines of a record for a string of P and F, one letter per round."""
    return tuple("Round %d: reviewer, %s, %s" % (i, "opus" if i == 3 else "sonnet", "PASS" if c == "P" else "FAIL")
                 for i, c in enumerate(letters, 1))


def record_path(root):
    return os.path.join(root, *RECORD_FOLDER, RECORD_NAME)


def shipped_text():
    with open(record_path(REPO), encoding="utf-8") as handle:
        return handle.read()


def table_span(lines, header):
    """-> (start, end) of the table under `header`: its header line through its last row, or None when no line is `header`."""
    if header not in lines:
        return None
    start = lines.index(header)
    end = start + 2  # the header and its separator
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return start, end


def policy_rows_of(text):
    """The cells of each review row in `text`, or None when the text holds no review rows table."""
    lines = text.split("\n")
    span = table_span(lines, POLICY_HEADER)
    if span is None:
        return None
    return [tuple(cell.strip() for cell in line.strip().strip("|").split("|")) for line in lines[span[0] + 2:span[1]]]


def with_policy(text, rows):
    """`text` with its review rows table set to `rows`: replaced in place, or added after the round table when it has none."""
    lines = text.split("\n")
    block = [POLICY_HEADER, POLICY_SEPARATOR] + ["| %s |" % " | ".join(row) for row in rows]
    span = table_span(lines, POLICY_HEADER)
    if span:
        lines[span[0]:span[1]] = block
    else:
        at = table_span(lines, ROUND_HEADER)[1]
        lines[at:at] = [""] + block
    return "\n".join(lines)


def checkout(rows=SHIPPED_ROWS):
    """A temp checkout whose record is the shipped record, its round-two row marked and its review rows table set to `rows`.
    -> the checkout's root, in this run's folder."""
    text = with_policy(shipped_text().replace(ROUND_TWO_ROW, ROUND_TWO_MARK), rows)
    root = tempfile.mkdtemp(dir=tm.run_folder())
    os.makedirs(os.path.dirname(record_path(root)))
    with open(record_path(root), "w", encoding="utf-8") as handle:
        handle.write(text)
    return root


def with_cell(kind, guard, column, value, rows=SHIPPED_ROWS):
    """`rows` with one cell of the (kind, guard) row set to `value`; column is "owed", "last" or "net"."""
    def cell(row):
        if row[:2] != (kind, guard):
            return row
        cells = list(row)
        cells[COLUMN[column]] = value
        return tuple(cells)
    return tuple(cell(row) for row in rows)


def without(kind, guard, rows=SHIPPED_ROWS):
    """`rows` with the (kind, guard) row removed."""
    return tuple(row for row in rows if row[:2] != (kind, guard))


@contextlib.contextmanager
def pointed_at(root):
    """The guard's pointer checkout is `root` in the block, so the round rows and the review rows come from its record."""
    with unittest.mock.patch.object(hook_guard, "pointer_checkout", return_value=root):
        yield


def assert_reader_reads(test, root):
    """Scope before verdict: the round-row reader reads the record at `root`. That record's round two row is the marker."""
    with pointed_at(root):
        test.assertEqual(merge.review_round_model(2), "haiku",
                         "the round-row reader does not read the pointer checkout's record, so a verdict read here proves nothing")


def state_of(test, root, kind, guard, letters, fix=None, net="not owed"):
    """-> (state, why) of a record of this kind and Guard or check, with the rounds `letters`, a fix check `fix` (P, F or None) and
    the net value `net`, read through the pointer checkout at `root`."""
    rounds = round_lines(letters)
    with pointed_at(root):
        if fix is None:
            return tm.record_verdict(test, tm.record_text(rounds=rounds, kind=kind, guard=guard, net=net))
        return tm.fix_state(test, tm.REVIEW_FIX_PASS if fix == "P" else tm.REVIEW_FIX_FAIL, rounds=rounds, kind=kind, guard=guard, net=net)


class ShippedReviewRows(unittest.TestCase):
    """Case 1: the shipped record holds the review rows the policy states, and review_state gives the policy's verdict for every kind,
    Guard or check and round combination, round 2 FAIL with round 3 owed included."""

    def test_the_shipped_record_holds_the_review_rows_the_policy_states(self):
        rows = policy_rows_of(shipped_text())
        self.assertIsNotNone(rows, f"{RECORD_NAME} holds no review rows table, so review_state has no row to read: the rows are not read")
        self.assertEqual(rows, [tuple(row) for row in SHIPPED_ROWS], "the review rows of the shipped record are not the policy's rows")

    def test_the_shipped_rows_give_the_policy_verdict_for_every_kind_guard_and_round(self):
        self.assertIsNotNone(policy_rows_of(shipped_text()), f"{RECORD_NAME} holds no review rows table, so review_state has no row to read: the rows are not read")
        for kind, guard, letters, fix, net, want in MATRIX:
            with self.subTest(kind=kind, guard=guard, rounds=letters, fix=fix, net=net):
                state, why = state_of(self, REPO, kind, guard, letters, fix, net)
                self.assertEqual(state, want, f"review_state gives {state} for {kind}, Guard or check {guard}, rounds {letters or 'none'}: {why!r}")


class ReviewRowsRead(unittest.TestCase):
    """Case 2: a changed review row in a temp checkout's record changes review_state's verdict, with no code edit. Each case states the
    control (the shipped row, which the old code already gives) beside the changed row, and the changed row is the red."""

    def test_a_row_owing_two_rounds_after_a_pass_leaves_a_round_one_pass_open(self):
        control, changed = checkout(), checkout(with_cell("normal", "no", "owed", "2"))
        assert_reader_reads(self, control)
        assert_reader_reads(self, changed)
        self.assertEqual(state_of(self, control, "normal", "no", "P")[0], "done", "the control, the shipped row, does not read a round 1 PASS as done")
        state, why = state_of(self, changed, "normal", "no", "P")
        self.assertEqual(state, "open", f"a row owing 2 rounds after a pass reads a round 1 PASS as {state}, the rows are not read: {why!r}")

    def test_a_row_with_last_round_two_makes_a_round_two_fail_final_for_normal_no(self):
        control, changed = checkout(), checkout(with_cell("normal", "no", "last", "2"))
        assert_reader_reads(self, control)
        assert_reader_reads(self, changed)
        self.assertEqual(state_of(self, control, "normal", "no", "FF")[0], "open", "the control, the shipped row, does not hold a round 2 FAIL open")
        state, why = state_of(self, changed, "normal", "no", "FF")
        self.assertEqual(state, "done", f"a row with last round 2 reads a round 2 FAIL as {state}, the rows are not read: {why!r}")

    def test_a_row_with_last_round_three_keeps_a_delete_only_round_one_fail_open(self):
        control, changed = checkout(), checkout(with_cell("delete-only", "no", "last", "3"))
        assert_reader_reads(self, control)
        assert_reader_reads(self, changed)
        self.assertEqual(state_of(self, control, "delete-only", "no", "F")[0], "done", "the control, the shipped row, does not close a delete-only round 1 FAIL")
        state, why = state_of(self, changed, "delete-only", "no", "F")
        self.assertEqual(state, "open", f"a row with last round 3 reads a delete-only round 1 FAIL as {state}, the rows are not read: {why!r}")

    def test_a_net_value_cell_of_no_makes_a_failed_final_round_on_a_guard_change_done(self):
        control, changed = checkout(), checkout(with_cell("normal", "yes", "net", "no"))
        assert_reader_reads(self, control)
        assert_reader_reads(self, changed)
        self.assertEqual(state_of(self, control, "normal", "yes", "FFF")[0], "open", "the control, the shipped row, does not hold a failed final round's unowed net value open")
        state, why = state_of(self, changed, "normal", "yes", "FFF")
        self.assertEqual(state, "done", f"a row with no net value owed reads a failed final round as {state}, the rows are not read: {why!r}")

    def test_a_row_owing_one_round_leaves_a_docs_only_change_with_no_round_open(self):
        control, changed = checkout(), checkout(with_cell("docs-only", "no", "owed", "1"))
        assert_reader_reads(self, control)
        assert_reader_reads(self, changed)
        self.assertEqual(state_of(self, control, "docs-only", "no", "")[0], "done", "the control, the shipped row, does not close a docs-only change with no round")
        state, why = state_of(self, changed, "docs-only", "no", "")
        self.assertEqual(state, "open", f"a row owing 1 round reads a docs-only change with no round as {state}, the rows are not read: {why!r}")


class ReviewRowsFallback(unittest.TestCase):
    """Case 3: a missing or unreadable review row falls back to the built-in rule, which equals the shipped rows. Each case shows the
    fallback as a control, then a changed sibling row, which is the red: review_state must still read the rows it has."""

    def test_a_missing_row_falls_back_to_the_policy_verdict_and_a_sibling_row_is_still_read(self):
        missing = checkout(without("delete-only", "yes"))
        assert_reader_reads(self, missing)
        for letters, want in (("", "open"), ("P", "done"), ("F", "open"), ("FP", "done"), ("FFF", "open")):
            with self.subTest(rounds=letters):
                state, why = state_of(self, missing, "delete-only", "yes", letters)
                self.assertEqual(state, want, f"a missing delete-only, Guard or check yes row gives {state} for rounds {letters or 'none'}, not the policy's {want}: {why!r}")
        sibling = checkout(with_cell("normal", "no", "owed", "2"))
        assert_reader_reads(self, sibling)
        state, why = state_of(self, sibling, "normal", "no", "P")
        self.assertEqual(state, "open", f"a sibling row owing 2 rounds reads a round 1 PASS as {state}, the rows are not read: {why!r}")

    def test_an_unreadable_row_falls_back_to_the_policy_verdict_and_a_readable_sibling_is_still_read(self):
        unreadable = checkout(with_cell("normal", "no", "owed", "two"))
        assert_reader_reads(self, unreadable)
        for kind, guard, letters, fix, net, want in NORMAL_NO:
            with self.subTest(rounds=letters, fix=fix, net=net):
                state, why = state_of(self, unreadable, kind, guard, letters, fix, net)
                self.assertEqual(state, want, f"an unreadable normal, no row gives {state} for rounds {letters or 'none'}, not the policy's {want}: {why!r}")
        sibling = checkout(with_cell("delete-only", "no", "last", "3"))
        assert_reader_reads(self, sibling)
        state, why = state_of(self, sibling, "delete-only", "no", "F")
        self.assertEqual(state, "open", f"a readable delete-only, Guard or check no row with last round 3 reads a round 1 FAIL as {state}, the rows are not read: {why!r}")

    def test_a_table_with_no_rows_or_no_record_falls_back_and_a_one_row_table_is_still_read(self):
        empty = checkout(())
        assert_reader_reads(self, empty)
        no_record = tempfile.mkdtemp(dir=tm.run_folder())
        self.assertIsNone(hook_guard.role_round_table(no_record), "the empty folder holds a record, so the fallback is not what is read here")
        for root in (empty, no_record):
            for kind, guard, letters, fix, net, want in NORMAL_NO:
                with self.subTest(root=os.path.basename(root), rounds=letters, fix=fix, net=net):
                    state, why = state_of(self, root, kind, guard, letters, fix, net)
                    self.assertEqual(state, want, f"with no review row, review_state gives {state} for rounds {letters or 'none'}, not the policy's {want}: {why!r}")
        one_row = checkout((("normal", "no", "2", "3", "no"),))
        assert_reader_reads(self, one_row)
        state, why = state_of(self, one_row, "normal", "no", "P")
        self.assertEqual(state, "open", f"a one-row table owing 2 rounds reads a round 1 PASS as {state}, the rows are not read: {why!r}")
        self.assertIsNotNone(getattr(hook_guard, "REVIEW_POLICY_FALLBACK", None),
                             "hooks/guard.py names no review policy fallback constant, so the built-in rule is not named")


if __name__ == "__main__":
    unittest.main()
