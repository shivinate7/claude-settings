#!/usr/bin/env python3
"""The review tally: `merge --review-tally --since <iso> [--split <iso>]` counts review outcomes from the review records.

The tally makes one list read of the repo's issue comments, from --since (Host.issue_comments). It reads no other route, writes no
file and starts no timer, so its whole cost is that read (rule outcomes-mechanize-rules). A comment counts as a record only when the
review marker is its first line. The record form is decision pr-review-record; parse_review in merge/merge.py reads it.

Readings the cases pin:
- A pull request counts from its first record with a first-round line. A record before that one, with no such line, is skipped.
- A record whose PR line names another pull request does not count on the thread it is posted on: it neither starts that thread's
  pull request nor sets its split side (own_records reads the PR line the same way).
- The first round counts once per pull request, from that first record. A later record reprints the first round, so it is not counted again.
- Round N above 1 counts once, from the first record of that pull request that holds a Round N line. A record posted after a round
  reprints the earlier rounds, and a second-round line sits only in a record that opens at the first round. So the first record of
  the first round alone would leave the second and third rounds empty. The first later record and the newest one give the same line.
- A first-round FAIL reads as second-round PASS, second-round FAIL, or none (no record of the pull request holds a second-round line).
- A design-reviewer line is no round. It counts in no table, and it neither starts a pull request nor sets its split side.
- A record that parse_review refuses counts as unknown. It drops nothing: a later record that reprints its rounds still counts them.
- --split sorts each pull request by the created time of the record it starts at: before the split, or after it. A record created at
  exactly the split counts after it. Without --split, one section, `all`, holds every pull request. The other cases keep each record
  away from the split instant.
- A failed comment read prints `unknown` and exits non-zero. It never prints a count (rule verification-report-unknown-reads).
Left open, and not pinned: where a record whose PR line names another pull request counts (the cases assert only its own thread),
and whether an unparseable record with no first-round line counts as unknown.

Printed contract, which the builder matches and parse_tally reads:
    before the split                          a section header: `before the split`, `after the split`, or `all`
    round N, haiku: PASS 37, FAIL 146         one line per round and model in each section
    first-round FAIL, then second round: PASS 1, FAIL 0, none 0
    unknown: 0

Each case calls merge.main with the GitHub half faked by test_merge's PullsHost. The first assert of each case checks the exit code, so
a refused flag fails there with its text. The controls at the end read only the fixtures and the comment read, and do not depend on the tally.
Run: python3 merge/test_review_tally.py
"""
import contextlib, io, os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge  # noqa: E402  the tally's home (merge/merge.py)
import test_merge as tm  # noqa: E402  the GitHub half (PullsHost) and the review record fixtures (record_text, review_comment)

SINCE = "2026-11-14T00:00:00Z"
OTHER_SINCE = "2026-11-01T00:00:00Z"  # a second --since: the read must start there, not at a built-in date
SPLIT = "2026-11-17T00:00:00Z"
JUST_BEFORE_SPLIT = "2026-11-16T23:59:59Z"  # one second before SPLIT: the split's own instant is the boundary case
EARLY, LATER, LATEST = "2026-11-15T09:00:00Z", "2026-11-15T10:00:00Z", "2026-11-15T11:00:00Z"  # all before the split
LATE = "2026-11-17T09:00:00Z"  # after the split
SECTION_BEFORE, SECTION_AFTER, SECTION_ALL = "before the split", "after the split", "all"

HAIKU_FAIL = "Round 1: reviewer, haiku, FAIL"
HAIKU_PASS = "Round 1: reviewer, haiku, PASS"
SONNET_PASS = "Round 1: reviewer, sonnet, PASS"
SONNET_FAIL = "Round 1: reviewer, sonnet, FAIL"
SONNET_R2_PASS = "Round 2: reviewer, sonnet, PASS"
SONNET_R2_FAIL = "Round 2: reviewer, sonnet, FAIL"
OPUS_R3_PASS = "Round 3: reviewer, opus, PASS"
DESIGN_R1_FAIL = "Round 1: design-reviewer, opus, FAIL"  # the design reviewer runs opus, and no reviewer line in these cases does
DESIGN_R1_PASS = "Round 1: design-reviewer, opus, PASS"
FIX_VERIFIER = f"Fix check: {tm.REVIEW_OLD_HEAD}, reviewer, sonnet, PASS"
UNPARSEABLE = "Round 1: reviewer, haiku, MAYBE"  # a verdict parse_review refuses

ROUND_LINE = re.compile(r"round (\d+), (\S+): PASS (\d+), FAIL (\d+)")
FOLLOW_LINE = re.compile(r"round 1 FAIL, then round 2: PASS (\d+), FAIL (\d+), none (\d+)")
UNKNOWN_LINE = re.compile(r"unknown: (\d+)")
EMPTY = {"rounds": {}, "follow": (0, 0, 0), "unknown": 0}


def parse_tally(out):
    """-> {section: {"rounds": {(round, model): (PASS, FAIL)}, "follow": (PASS, FAIL, none), "unknown": n}}, one entry per section header printed."""
    sections, current = {}, None
    for raw in out.splitlines():
        line = raw.strip()
        if line in (SECTION_BEFORE, SECTION_AFTER, SECTION_ALL):
            current = sections[line] = {"rounds": {}, "follow": (0, 0, 0), "unknown": 0}
        elif current is None:
            continue
        elif m := ROUND_LINE.fullmatch(line):
            current["rounds"][(int(m.group(1)), m.group(2))] = (int(m.group(3)), int(m.group(4)))
        elif m := FOLLOW_LINE.fullmatch(line):
            current["follow"] = tuple(int(x) for x in m.groups())
        elif m := UNKNOWN_LINE.fullmatch(line):
            current["unknown"] = int(m.group(1))
    return sections


def rounds(out, section, n, model):
    """-> (PASS, FAIL) printed for round n of `model` in `section`; (0, 0) when no such line is printed."""
    return parse_tally(out).get(section, EMPTY)["rounds"].get((n, model), (0, 0))


def follow(out, section):
    """-> (PASS, FAIL, none) printed for the first-round FAILs of `section`: how the second round went."""
    return parse_tally(out).get(section, EMPTY)["follow"]


def unknown(out, section):
    """-> the unknown count printed for `section`; 0 when none is printed."""
    return parse_tally(out).get(section, EMPTY)["unknown"]


def round_one_total(out, section):
    """-> the first-round PASS and FAIL of every model in `section`, summed."""
    return sum(p + f for (n, _), (p, f) in parse_tally(out).get(section, EMPTY)["rounds"].items() if n == 1)


def any_count(out):
    """True when the output prints a round count above zero in any section."""
    return any(v != (0, 0) for section in parse_tally(out).values() for v in section["rounds"].values())


def run_tally(host, *argv):
    """-> (rc, output) of `merge --review-tally <argv>` through merge.main, with `host` as the GitHub half. A usage refusal exits through
    argparse, so its exit code is the rc and its text is in the output."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            rc = merge.main(["--review-tally", *argv], host=host)
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue()


def last_line(out):
    """-> the last non-blank line of `out`: a usage refusal ends with its reason."""
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


def comment(cid, n, body, created):
    """A repo-wide issue comment on pull request n, created at `created`."""
    return tm.review_comment(cid, n, body, created=created)


def record(n, *rounds_, fix=()):
    """A review record for pull request n with the given Round lines, in the form parse_review reads."""
    return tm.record_text(n=n, rounds=rounds_, fix=fix)


class TallyCase(unittest.TestCase):
    def tally(self, comments, *argv, since=SINCE):
        """-> the printed tally of one run over `comments`. Scope first: the run exits 0 and makes exactly one read of the issue comments, from `since`."""
        host = tm.PullsHost([], {}, comments=comments)
        rc, out = run_tally(host, "--since", since, *argv)
        self.assertEqual(rc, 0, f"merge --review-tally exited {rc}, not 0: {last_line(out)}")
        reads = [(rel, f.get("since")) for rel, f in host.list_calls]
        self.assertTrue(reads == [("issues/comments", since)], f"the tally must read the issue comments once, from --since: {reads}")
        return out


class RoundCounts(TallyCase):
    def test_a_round_one_fail_passed_by_round_two_in_one_record_counts_both(self):
        comments = [comment(1, 7, record(7, HAIKU_FAIL, SONNET_R2_PASS), EARLY)]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 1), f"round 1 haiku FAIL before the split: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 2, "sonnet"), (1, 0), f"round 2 sonnet PASS before the split: {out}")
        self.assertEqual(follow(out, SECTION_BEFORE), (1, 0, 0), f"a round 1 FAIL that round 2 passed in the same record: {out}")

    def test_round_one_counts_once_and_round_two_is_read_from_a_later_record(self):
        comments = [
            comment(1, 7, record(7, HAIKU_FAIL), EARLY),
            comment(2, 7, record(7, HAIKU_FAIL, SONNET_R2_PASS), LATER),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 1),
                         f"round 1 FAIL counts once, though the later record reprints it: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 2, "sonnet"), (1, 0), f"round 2 PASS is read from the later record: {out}")
        self.assertEqual(follow(out, SECTION_BEFORE), (1, 0, 0), f"a round 1 FAIL that a later record shows round 2 passing: {out}")

    def test_rounds_two_and_three_each_count_once_from_the_first_record_that_holds_them(self):
        comments = [
            comment(1, 7, record(7, HAIKU_FAIL), EARLY),
            comment(2, 7, record(7, HAIKU_FAIL, SONNET_R2_FAIL), LATER),
            comment(3, 7, record(7, HAIKU_FAIL, SONNET_R2_FAIL, OPUS_R3_PASS), LATEST),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 1), f"round 1 haiku FAIL counts once across three records: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 2, "sonnet"), (0, 1), f"round 2 sonnet FAIL counts once across three records: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 3, "opus"), (1, 0), f"round 3 opus PASS is counted under round 3: {out}")
        self.assertEqual(follow(out, SECTION_BEFORE), (0, 1, 0), f"a round 1 FAIL that round 2 failed reads as FAIL, not none: {out}")

    def test_a_first_record_with_no_round_one_line_is_skipped_and_the_next_one_counts(self):
        comments = [
            comment(1, 7, record(7, fix=(FIX_VERIFIER,)), EARLY),
            comment(2, 7, record(7, SONNET_FAIL), LATER),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "sonnet"), (0, 1),
                         f"the record with no Round 1 line is skipped, so the later round 1 record counts: {out}")
        self.assertEqual(unknown(out, SECTION_BEFORE), 0, f"a skipped record that parses is not unknown: {out}")

    def test_a_design_reviewer_line_is_no_round(self):
        comments = [comment(1, 7, record(7, SONNET_FAIL, DESIGN_R1_PASS), EARLY)]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(round_one_total(out, SECTION_BEFORE), 1,
                         f"a design-reviewer round 1 line was counted as a round, beside the reviewer's one: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "opus"), (0, 0), f"the design reviewer's opus line is in the table: {out}")


class SplitAndSections(TallyCase):
    def test_each_pull_request_lands_before_or_after_the_split_by_when_its_record_was_posted(self):
        comments = [
            comment(1, 7, record(7, SONNET_PASS), EARLY),
            comment(2, 8, record(8, HAIKU_FAIL), LATE),
            comment(3, 9, record(9, HAIKU_PASS), LATE),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "sonnet"), (1, 0), f"the record posted before the split: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 0), f"no record posted after the split counts before it: {out}")
        self.assertEqual(rounds(out, SECTION_AFTER, 1, "haiku"), (1, 1), f"the two records posted after the split: {out}")
        self.assertEqual(rounds(out, SECTION_AFTER, 1, "sonnet"), (0, 0), f"the record posted before the split counts after it: {out}")

    def test_without_a_split_one_all_section_holds_every_record(self):
        comments = [
            comment(1, 7, record(7, SONNET_PASS), EARLY),
            comment(2, 8, record(8, HAIKU_FAIL), LATE),
            comment(3, 9, record(9, HAIKU_PASS), LATE),
        ]
        out = self.tally(comments)
        self.assertEqual(set(parse_tally(out)), {SECTION_ALL}, f"without --split the output holds one section: {out}")
        self.assertEqual(rounds(out, SECTION_ALL, 1, "sonnet"), (1, 0), f"the sonnet record in the all section: {out}")
        self.assertEqual(rounds(out, SECTION_ALL, 1, "haiku"), (1, 1), f"both haiku records in the all section: {out}")

    def test_a_design_reviewer_round_one_line_does_not_set_its_pull_requests_split_side(self):
        comments = [
            comment(1, 7, record(7, DESIGN_R1_FAIL), EARLY),
            comment(2, 7, record(7, SONNET_PASS), LATE),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "sonnet"), (0, 0),
                         f"the design reviewer's round 1 line, in an earlier record, put pull request 7 before the split: {out}")
        self.assertEqual(rounds(out, SECTION_AFTER, 1, "sonnet"), (1, 0),
                         f"the reviewer's round 1 record, posted after the split, does not count after it: {out}")

    def test_a_record_at_exactly_the_split_counts_after_it(self):
        comments = [
            comment(1, 7, record(7, SONNET_PASS), JUST_BEFORE_SPLIT),
            comment(2, 8, record(8, HAIKU_FAIL), SPLIT),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "sonnet"), (1, 0),
                         f"the record one second before the split does not count before it: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 0),
                         f"the record at exactly the split counts before it: {out}")
        self.assertEqual(rounds(out, SECTION_AFTER, 1, "haiku"), (0, 1),
                         f"the record at exactly the split does not count after it: {out}")


class UnknownsAndNonRecords(TallyCase):
    def test_an_unparseable_first_record_is_unknown_and_its_pull_request_counts_no_round(self):
        comments = [
            comment(1, 7, record(7, UNPARSEABLE), EARLY),
            comment(2, 8, record(8, SONNET_PASS), EARLY),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(unknown(out, SECTION_BEFORE), 1, f"the refused record is counted as unknown, not dropped: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 0), f"a refused record counts no round: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "sonnet"), (1, 0), f"the parseable record still counts: {out}")
        self.assertEqual(round_one_total(out, SECTION_BEFORE) + unknown(out, SECTION_BEFORE), 2,
                         f"every pull request with a round 1 record is counted or unknown: {out}")

    def test_a_comment_whose_first_line_is_not_the_marker_is_not_counted(self):
        plain = "Round 1: reviewer, haiku, FAIL\nNet value: not owed\n"
        note_first = "A note first.\n" + record(7, HAIKU_FAIL)
        comments = [comment(1, 7, plain, EARLY), comment(2, 7, note_first, LATER)]
        out = self.tally(comments, "--split", SPLIT)
        self.assertFalse(any_count(out), f"a comment that is not a review record was counted: {out}")
        self.assertEqual(unknown(out, SECTION_BEFORE), 0, f"a comment that is not a review record is not unknown either: {out}")

    def test_a_failed_comment_read_prints_unknown_and_no_count(self):
        host = tm.PullsHost([], {}, comments=[], comments_error="reading issues/comments failed: HTTP 500: Server Error")
        rc, out = run_tally(host, "--since", SINCE, "--split", SPLIT)
        reads = [rel for rel, _ in host.list_calls]
        self.assertTrue(reads == ["issues/comments"], f"the tally did not read the comments (exit {rc}: {last_line(out)}): {reads}")
        self.assertNotEqual(rc, 0, f"a failed read exited 0, so it reads as clear: {out}")
        self.assertIn("unknown", out, f"a failed read is not reported as unknown: {out}")
        self.assertFalse(any_count(out), f"a failed read printed a count: {out}")

    def test_a_record_that_names_another_pull_request_is_not_counted_on_the_thread_it_is_posted_on(self):
        # Posted on pull request 7's thread, the record's PR line names pull request 8, so own_records would skip it for pull request 7.
        comments = [
            comment(1, 7, record(8, HAIKU_FAIL), EARLY),
            comment(2, 7, record(7, SONNET_PASS), LATE),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 0),
                         f"a record that names pull request 8 was counted on pull request 7's thread: {out}")
        self.assertEqual(rounds(out, SECTION_AFTER, 1, "sonnet"), (1, 0),
                         f"a record that names another pull request set pull request 7's split side: {out}")

    def test_a_refused_first_record_does_not_drop_the_corrected_reprint_after_it(self):
        comments = [
            comment(1, 7, record(7, UNPARSEABLE), EARLY),
            comment(2, 7, record(7, HAIKU_FAIL, SONNET_R2_PASS), LATER),
        ]
        out = self.tally(comments, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (0, 1),
                         f"the corrected reprint's round 1 FAIL is dropped after a refused first record: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 2, "sonnet"), (1, 0),
                         f"the corrected reprint's round 2 PASS is dropped after a refused first record: {out}")
        self.assertEqual(follow(out, SECTION_BEFORE), (1, 0, 0),
                         f"the round 1 FAIL of the corrected reprint has no round 2 read after a refused first record: {out}")
        self.assertEqual(unknown(out, SECTION_BEFORE), 1, f"the refused first record is not counted as unknown: {out}")


class EdgeStates(TallyCase):
    def test_the_read_starts_at_since_and_the_tally_reads_nothing_else(self):
        comments = [comment(1, 7, record(7, SONNET_PASS), EARLY)]
        out = self.tally(comments, "--split", SPLIT, since=OTHER_SINCE)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "sonnet"), (1, 0), f"the record read from the second --since: {out}")

    def test_an_empty_read_prints_no_count_and_exits_zero(self):
        out = self.tally([], "--split", SPLIT)
        self.assertFalse(any_count(out), f"an empty read printed a count: {out}")
        self.assertEqual(unknown(out, SECTION_BEFORE), 0, f"an empty read printed an unknown: {out}")
        self.assertEqual(unknown(out, SECTION_AFTER), 0, f"an empty read printed an unknown after the split: {out}")

    def test_the_full_one_off_counts_are_read_whole(self):
        # The first round of the one-off count (Nov 14-18): Haiku 37 PASS of 183 records, Sonnet 61 PASS of 141. Past one page of 100 comments.
        haiku = [comment(i, i, record(i, HAIKU_PASS if i <= 37 else HAIKU_FAIL), EARLY) for i in range(1, 184)]
        sonnet = [comment(i, i, record(i, SONNET_PASS if i - 183 <= 61 else SONNET_FAIL), EARLY) for i in range(184, 325)]
        out = self.tally(haiku + sonnet, "--split", SPLIT)
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "haiku"), (37, 146), f"all 183 Haiku records counted: {out}")
        self.assertEqual(rounds(out, SECTION_BEFORE, 1, "sonnet"), (61, 80), f"all 141 Sonnet records counted: {out}")
        self.assertEqual(unknown(out, SECTION_BEFORE), 0, f"no record is unknown in the full read: {out}")


class FixtureControls(unittest.TestCase):
    """Green on the old code too: the fixtures and the comment read already behave as the cases assume. So a red case fails on the tally,
    not on its own fixture."""

    def test_control_the_records_the_cases_count_parse_and_the_refused_one_does_not(self):
        for body in (record(7, HAIKU_FAIL, SONNET_R2_PASS), record(7, HAIKU_FAIL), record(7, fix=(FIX_VERIFIER,)),
                     record(7, HAIKU_FAIL, SONNET_R2_FAIL, OPUS_R3_PASS), record(7, DESIGN_R1_FAIL),
                     record(7, SONNET_FAIL, DESIGN_R1_PASS)):
            self.assertIsNotNone(merge.parse_review(body), f"fixture: a record the cases count does not parse:\n{body}")
        self.assertIsNone(merge.parse_review(record(7, UNPARSEABLE)), "fixture: the refused record parses, so it is not unknown")
        self.assertEqual(merge.parse_review(record(8, HAIKU_FAIL))["n"], 8, "fixture: a record whose PR line names 8 does not parse as 8")

    def test_control_the_comment_read_keeps_only_records_with_the_marker_first(self):
        good = record(7, HAIKU_FAIL)
        host = tm.PullsHost([], {}, comments=[comment(1, 7, good, EARLY), comment(2, 7, "Round 1: reviewer, haiku, FAIL\n", EARLY),
                                              comment(3, 7, "A note.\n" + good, LATER)])
        records = host.issue_comments(SINCE)[0]  # {PR number: [(body, created, updated)]}, the first of the read's parts
        kept = [body for body, _, _ in records.get(7, [])]
        self.assertTrue(kept == [good], f"the comment read kept the wrong records: {kept}")
        reads = [(rel, f.get("since")) for rel, f in host.list_calls]
        self.assertTrue(reads == [("issues/comments", SINCE)], f"the comment read did not start at --since: {reads}")


if __name__ == "__main__":
    unittest.main()
