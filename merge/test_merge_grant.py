#!/usr/bin/env python3
"""Suite for the Grant line of a review record (merge/merge.py) and for the --grant flag that goes with --review-record.

Run: python3 merge/test_merge_grant.py

A record with a Grant line may hold a fourth round, the one round past the usual limit of three. The cases here cover the
parser, the printed body, review_state's reading of round four, and the flag's usage errors.
The review-record fixtures (record_text, parse_text, review_fn and the REVIEW_* constants) and the flag base (ReviewEnv) come
from merge/test_merge.py: a case extends that fixture, it does not copy it. Importing it runs none of its cases.
"""
import inspect, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_merge as tm  # noqa: E402  the review-record fixtures and the flag base (ReviewEnv); importing it runs none of its cases

# A valid Grant text, the form a record's Grant line carries after "Grant: ": `#<pr>, <cite>`. The PR is the record's own PR (7 in these
# cases), and the cite is the owner's grant of one fourth round past the usual limit of three. GRANT_CITE is the cite part alone.
GRANT_CITE = "item 396 a, owner, 2026-11-08 06:08 CST"

def grant_text(pr=7, cite=GRANT_CITE):
    """The Grant text for pull request `pr`: `#<pr>, <cite>`. Every grant literal in the review-record cases is built here."""
    return f"#{pr}, {cite}"

REVIEW_GRANT = grant_text()
REVIEW_FOUR_ROUNDS = ((1, "reviewer", "sonnet", "FAIL"), (2, "reviewer", "sonnet", "FAIL"), (3, "reviewer", "opus", "FAIL"), (4, "reviewer", "opus", "PASS"))

def round_four_text(verdict="PASS"):
    """The Round lines of a record with a fourth round: the three rounds before it fail, then the fourth is `verdict`."""
    return tm.REVIEW_FAILED_THREE + (f"Round 4: reviewer, opus, {verdict}",)

def body_with_grant(test, rounds, net, grant):
    """review_body for pull request 7 at REVIEW_HEAD, a normal change with guard no, with the Grant text `grant`. A merge.py that takes no grant argument fails here by name."""
    fn = tm.review_fn(test, "review_body")
    if "grant" not in inspect.signature(fn).parameters:
        test.fail("merge.review_body takes no grant argument")
    return fn(7, tm.REVIEW_HEAD, "normal", "no", rounds, net, grant=grant)

class ReviewGrantForm(unittest.TestCase):
    """A record with a Grant line may hold a fourth round, the one round past the usual limit, and no more. The Grant
    line follows Guard or check and comes before the rounds, and its text is `#<pr>, <cite>`: the PR must be the record's own PR. parse_review
    returns its text as rec["grant"], and None without the line. Each refusal sits beside a well-formed sibling that must parse, so the case
    is red until the parser knows the line."""

    def test_a_grant_line_parses_to_its_text_and_round_four_parses(self):
        for zone in ("CST", "CDT"):
            with self.subTest(zone=zone):
                grant = grant_text(cite=f"item 396 a, owner, 2026-11-08 06:08 {zone}")
                rec = tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {grant}",)))
                self.assertEqual(rec.get("grant"), grant, f"the Grant line did not parse to its text: {rec.get('grant')!r}")
                self.assertEqual(rec["rounds"][-1], (4, "reviewer", "opus", "PASS"), "round 4 did not parse")

    def test_round_four_without_a_grant_is_not_a_record(self):
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))  # the sibling with the Grant line must parse
        self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=round_four_text())), "parse_review accepted round 4 with no Grant line")

    def test_round_five_is_not_a_record_even_with_a_grant(self):
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))
        five = round_four_text() + ("Round 5: reviewer, opus, PASS",)
        for grant in ((), (f"Grant: {REVIEW_GRANT}",)):
            with self.subTest(with_grant=bool(grant)):
                self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=five, grant=grant)), "parse_review accepted round 5")

    def test_a_grant_line_with_no_round_four_is_not_a_record(self):
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))
        for cause, rounds in (("rounds 1 to 3", tm.REVIEW_FAILED_THREE), ("round 1 only", tm.REVIEW_PASS), ("no round", ())):
            with self.subTest(cause=cause):
                self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=rounds, grant=(f"Grant: {REVIEW_GRANT}",))),
                                  f"parse_review accepted a Grant line with {cause}")

    def test_a_malformed_grant_line_is_not_a_record(self):
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))
        bad = {"an upper-case letter": grant_text(cite="item 396 A, owner, 2026-11-08 06:08 CST"),
               "no letter": grant_text(cite="item 396, owner, 2026-11-08 06:08 CST"),
               "two letters": grant_text(cite="item 396 ab, owner, 2026-11-08 06:08 CST"),
               "a zone other than CST or CDT": grant_text(cite="item 396 a, owner, 2026-11-08 06:08 PST"),
               "an unpadded day": grant_text(cite="item 396 a, owner, 2026-11-8 06:08 CST"),
               "no zone": grant_text(cite="item 396 a, owner, 2026-11-08 06:08"),
               "an owner that is not owner": grant_text(cite="item 396 a, lead, 2026-11-08 06:08 CST"),
               "a trailing space": f"{REVIEW_GRANT} ", "no cite": grant_text(cite=""),
               "a PR that is not digits": f"#7a, {GRANT_CITE}"}
        for cause, text in bad.items():
            with self.subTest(cause=cause):
                self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=round_four_text(), grant=(f"Grant: {text}",))),
                                  f"parse_review accepted a Grant line with {cause}")

    def test_a_grant_line_naming_another_pr_is_not_a_record(self):
        # A grant cite copied from another pull request does not grant this one, so the record is refused. The cite's number
        # must equal the record's own as a whole number: a longer number that only starts with or contains it is refused too.
        tm.parse_text(self, tm.record_text(n=9999, rounds=round_four_text(), grant=(f"Grant: {grant_text(9999)}",)))  # the sibling: its own PR parses
        tm.parse_text(self, tm.record_text(n=1979, rounds=round_four_text(), grant=(f"Grant: {grant_text(1979)}",)))
        for n, pr in ((9999, 1979), (1979, 19790), (1979, 197)):
            with self.subTest(record=n, grant=pr):
                self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(n=n, rounds=round_four_text(), grant=(f"Grant: {grant_text(pr)}",))),
                                  f"parse_review accepted a Grant line for PR {pr} on PR {n}")

    def test_a_grant_in_todays_form_with_no_pr_part_is_not_a_record(self):
        # The form before the PR part: `item N x, owner, ...` with no `#<pr>, `. That cite names no pull request, so a record that carries it
        # is not a record. The refusal comes first, so a parser that still takes the old form fails here by name.
        self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=round_four_text(), grant=(f"Grant: {GRANT_CITE}",))),
                          "parse_review accepted a Grant line with no #pr part")
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))  # the sibling: the same cite with its PR part parses

    def test_a_matching_pr_and_cite_parse_and_round_four_reads_final(self):
        rec = tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))
        self.assertEqual(rec.get("grant"), REVIEW_GRANT, f"the matching Grant line did not parse to its text: {rec.get('grant')!r}")
        state, why = tm.review_fn(self, "review_state")(rec, tm.REVIEW_HEAD)
        self.assertEqual(state, "done", f"round 4 is the final round of a granted record, and it reads {state!r}: {why!r}")
        self.assertIn("round 4", why, f"the why does not name round 4: {why!r}")

    def test_a_grant_line_after_the_round_lines_is_not_a_record(self):
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))  # the sibling: the Grant line before the rounds
        # the same line where the fix check goes, after the rounds: the form puts the Grant line before them, and the parser refuses a field out of order
        self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=round_four_text(), fix=(f"Grant: {REVIEW_GRANT}",))),
                          "parse_review accepted a Grant line after the round lines")

    def test_the_grant_line_round_trips_through_review_body(self):
        text = tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",))
        rec = tm.parse_text(self, text)
        self.assertEqual(tm.review_fn(self, "review_body")(**rec).splitlines(), text.splitlines())

    def test_review_body_prints_the_grant_line_after_guard_and_before_the_rounds(self):
        body = body_with_grant(self, REVIEW_FOUR_ROUNDS, "not owed", REVIEW_GRANT)
        self.assertEqual(body.splitlines(), [tm.REVIEW_MARKER, "PR: #7", f"Head: {tm.REVIEW_HEAD}", "Kind: normal", "Guard or check: no",
                                             f"Grant: {REVIEW_GRANT}", *round_four_text(), "Net value: not owed", tm.REVIEW_CI_LINE])

    def test_a_record_with_no_grant_line_has_a_none_grant_and_round_trips_unchanged(self):
        # the form on main: no Grant line gives grant None, and the body is byte-identical to the record
        cases = (tm.record_text(rounds=tm.REVIEW_PASS), tm.record_text(rounds=tm.REVIEW_FAILED_THREE, guard="yes", net="zero"),
                 tm.record_text(rounds=(), kind="docs-only"), tm.record_text(rounds=tm.REVIEW_PASS, fix=(tm.fix_verifier_line(),)))
        for i, text in enumerate(cases):
            with self.subTest(case=i):
                rec = tm.parse_text(self, text)
                self.assertIn("grant", rec, "parse_review returned no grant key for a record with no Grant line")
                self.assertIsNone(rec["grant"], f"a record with no Grant line has grant {rec['grant']!r}")
                self.assertEqual(tm.review_fn(self, "review_body")(**rec), text, "the body of a record with no Grant line is not byte-identical")

    def test_a_grant_on_an_impossible_date_is_not_a_record(self):
        # the sibling dates are real, a leap day among them, so each refusal below is for the date alone
        for date in ("2026-11-08 06:08 CST", "2028-02-29 06:08 CDT"):
            with self.subTest(sibling=date):
                tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {grant_text(cite=f'item 396 a, owner, {date}')}",)))
        for date in ("2026-99-99 25:99 CST", "2026-02-30 06:08 CST"):
            with self.subTest(date=date):
                text = grant_text(cite=f"item 396 a, owner, {date}")
                self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=round_four_text(), grant=(f"Grant: {text}",))),
                                  f"parse_review accepted a Grant line with the impossible date {date!r}")

    def test_two_grant_lines_are_not_a_record(self):
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))  # the sibling: one Grant line parses
        two = (f"Grant: {REVIEW_GRANT}", f"Grant: {grant_text(cite='item 397 b, owner, 2026-11-08 06:08 CST')}")
        self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=round_four_text(), grant=two)), "parse_review accepted two Grant lines")

    def test_a_grant_line_with_unicode_digits_is_not_a_record(self):
        tm.parse_text(self, tm.record_text(rounds=round_four_text(), grant=(f"Grant: {REVIEW_GRANT}",)))  # the sibling: ASCII digits parse
        # fullwidth digits in the PR number, in the item number, and Arabic-Indic digits in the year
        for cause, text in (("fullwidth digits in the PR", f"#７, {GRANT_CITE}"),
                            ("fullwidth digits", grant_text(cite="item ３９６ a, owner, 2026-11-08 06:08 CST")),
                            ("Arabic-Indic digits", grant_text(cite="item 396 a, owner, ٢٠٢٦-11-08 06:08 CST"))):
            with self.subTest(cause=cause):
                self.assertIsNone(tm.review_fn(self, "parse_review")(tm.record_text(rounds=round_four_text(), grant=(f"Grant: {text}",))),
                                  f"parse_review accepted a Grant line with {cause}")

class ReviewGrantRules(unittest.TestCase):
    """review_state over a record with a Grant line. The fourth round is the last one a grant allows, and it follows the rules of the last round with no grant. The why
    names the fourth round, not the third. Design-reviewer lines stay out of these cases, so the why carries no design note."""

    def granted_state(self, verdict, **kw):
        """-> (state, why) of a record with a Grant line whose fourth round is `verdict`; the rest of the form comes from `kw`."""
        return tm.record_verdict(self, tm.record_text(rounds=round_four_text(verdict), grant=(f"Grant: {REVIEW_GRANT}",), **kw))

    def assert_names_round_four(self, why):
        self.assertIn("round 4", why, f"the why does not name round 4: {why!r}")
        self.assertNotIn("round 3", why, f"the why names round 3, not round 4: {why!r}")

    def test_round_four_with_guard_no_is_done_whatever_its_verdict(self):
        for verdict in ("PASS", "FAIL", "PARTIAL"):
            with self.subTest(verdict=verdict):
                state, why = self.granted_state(verdict, guard="no")
                self.assertEqual(state, "done", "round 4 is the final round, and with guard no it is done whatever its verdict")
                self.assert_names_round_four(why)

    def test_round_four_with_guard_yes_is_done_when_net_value_is_zero_or_positive(self):
        # the fourth round's verdict is FAIL, so the net value alone decides done
        for net in ("zero", "positive"):
            with self.subTest(net=net):
                state, why = self.granted_state("FAIL", guard="yes", net=net)
                self.assertEqual(state, "done", f"round 4 with net value {net} is done")
                self.assert_names_round_four(why)

    def test_round_four_with_guard_yes_is_held_when_net_value_is_negative(self):
        self.assertEqual(self.granted_state("FAIL", guard="yes", net="negative")[0], "held")

    def test_round_four_with_guard_yes_is_open_when_net_value_is_not_written(self):
        for verdict in ("FAIL", "PASS"):
            with self.subTest(verdict=verdict):
                state, why = self.granted_state(verdict, guard="yes", net="not owed")
                self.assertEqual(state, "open", "a net value the guard change owes is not settled by round 4")
                self.assert_names_round_four(why)

    def test_a_round_four_pass_with_guard_yes_owes_the_net_value_test(self):
        for net, want in (("not owed", "open"), ("zero", "done"), ("positive", "done"), ("negative", "held")):
            with self.subTest(net=net):
                self.assertEqual(self.granted_state("PASS", guard="yes", net=net)[0], want)

    def test_a_granted_fourth_round_with_a_fix_check_reads_the_fix_on_the_fourth_round(self):
        # the allowed case: a granted record with a valid Fix check line parses, and its PASS is read on the fourth round
        for guard, net in (("no", "not owed"), ("yes", "zero")):
            with self.subTest(guard=guard, net=net):
                text = tm.record_text(rounds=round_four_text("PASS"), grant=(f"Grant: {REVIEW_GRANT}",), guard=guard, net=net, fix=(tm.fix_verifier_line(),))
                rec = tm.parse_text(self, text)
                self.assertEqual(rec.get("fix"), tm.REVIEW_FIX_PASS, f"the fix line did not parse on a granted record: {rec.get('fix')!r}")
                state, why = tm.review_fn(self, "review_state")(rec, tm.REVIEW_HEAD)
                self.assertEqual(state, "done", f"a granted fourth round with a fix PASS reads {state!r}: {why!r}")
                self.assert_names_round_four(why)

class ReviewGrantFlag(tm.ReviewEnv):
    """`--grant TEXT` goes with --review-record and lets a fourth round in: the one round past the usual limit. Its text is `#<pr>, <cite>`,
    and its PR must be the positional PR. Every refusal sits beside the good value, which must exit 0, so a parser that never learned the
    flag fails there too. A usage error prints no record."""

    THREE = ("--round", "1:reviewer:sonnet:FAIL", "--round", "2:reviewer:sonnet:FAIL", "--round", "3:reviewer:opus:FAIL")
    FOUR = (*THREE, "--round", "4:reviewer:opus:PASS")

    def granted(self, *tail, rounds=FOUR, pr="7"):
        """The review flags for a normal change with guard no at the live head, for pull request `pr`, with `rounds`, then `tail`."""
        return (pr, "--review-record", "--kind", "normal", "--guard", "no", "--head", self.head(), *rounds, *tail)

    def test_a_grant_naming_another_pr_is_a_usage_error(self):
        # A merge run for one pull request, with a grant cite copied from another, is refused. The control, with the grant for its
        # own pull request, must exit 0: the same form passes there, so only the pull request differs. A parser that never learned
        # the pull request part fails at the control.
        rc, out, err = self.run_args(*self.granted("--grant", grant_text(2005), pr="2005"))
        self.assertEqual(rc, 0, "merge refused the matching --grant for pull request 2005:\n" + out + err)
        out, _err = self.assert_usage_error(*self.granted("--grant", grant_text(1979), pr="2005"))
        self.assertNotIn(tm.REVIEW_MARKER, out)

    def test_round_four_with_a_grant_passes_and_prints_the_grant_line_after_guard(self):
        rc, out, err = self.run_args(*self.granted("--grant", REVIEW_GRANT))
        self.assertEqual(rc, 0, "merge refused --round 4 with --grant:\n" + out + err)
        body = tm.posted_body(self, out)
        self.assertEqual(body.splitlines()[4:6], ["Guard or check: no", f"Grant: {REVIEW_GRANT}"], "the Grant line is not after Guard or check:\n" + body)
        self.assertEqual(tm.parse_text(self, body).get("grant"), REVIEW_GRANT)

    def test_round_four_without_a_grant_refuses_with_the_message_it_has_today(self):
        rc, out, err = self.run_args(*self.granted("--grant", REVIEW_GRANT))  # the sibling: the same rounds with the grant pass
        self.assertEqual(rc, 0, "merge refused --round 4 with --grant:\n" + out + err)
        out, err = self.assert_usage_error(*self.granted())
        self.assertIn("--round: the rounds must start at 1, rise by one at a time and stop at 3", err)
        self.assertNotIn(tm.REVIEW_MARKER, out)

    def test_round_five_with_a_grant_refuses(self):
        rc, out, err = self.run_args(*self.granted("--grant", REVIEW_GRANT))
        self.assertEqual(rc, 0, "merge refused --round 4 with --grant:\n" + out + err)
        out, _err = self.assert_usage_error(*self.granted("--round", "5:reviewer:opus:PASS", "--grant", REVIEW_GRANT))
        self.assertNotIn(tm.REVIEW_MARKER, out)

    def test_grant_needs_review_record(self):
        argv = self.granted("--grant", REVIEW_GRANT)
        rc, out, err = self.run_args(*argv)
        self.assertEqual(rc, 0, "merge refused the good --grant:\n" + out + err)
        without = tuple(a for a in argv if a != "--review-record")  # the same argv with the one flag that makes it a record taken away
        out, _err = self.assert_usage_error(*without)
        self.assertNotIn(tm.REVIEW_MARKER, out)

    def test_a_malformed_grant_exits_two_and_prints_no_record(self):
        rc, out, err = self.run_args(*self.granted("--grant", REVIEW_GRANT))
        self.assertEqual(rc, 0, "merge refused the good --grant:\n" + out + err)
        bad = (grant_text(cite="item 396 A, owner, 2026-11-08 06:08 CST"), grant_text(cite="item 396, owner, 2026-11-08 06:08 CST"),
               grant_text(cite="item 396 a, owner, 2026-11-08 06:08 PST"), grant_text(cite="item 396 a, owner, 2026-11-8 06:08 CST"),
               grant_text(cite="item 396 a, lead, 2026-11-08 06:08 CST"), grant_text(cite="item 396 a, owner, 2026-11-08 06:08"),
               f"#x, {GRANT_CITE}", GRANT_CITE)  # the last one is today's form, with no #pr part: it is a usage error now
        for text in bad:
            with self.subTest(bad=text):
                out, _err = self.assert_usage_error(*self.granted("--grant", text))
                self.assertNotIn(tm.REVIEW_MARKER, out)

    def test_grant_with_no_round_four_refuses(self):
        rc, out, err = self.run_args(*self.granted("--grant", REVIEW_GRANT))
        self.assertEqual(rc, 0, "merge refused the good --grant:\n" + out + err)
        out, _err = self.assert_usage_error(*self.granted("--grant", REVIEW_GRANT, rounds=self.THREE))
        self.assertNotIn(tm.REVIEW_MARKER, out)

    def test_without_a_grant_the_usage_line_is_the_one_the_tool_prints(self):
        # with no --grant, the flags that go with --review-record are named exactly as main names them, so the whole line is compared
        rc, out, err = self.run_args("7", "--head", tm.REVIEW_HEAD)
        self.assertEqual(rc, 2, out + err)
        messages = [line.split(": error: ", 1)[1] for line in err.splitlines() if ": error: " in line]
        self.assertIn("--head, --kind, --guard, --round, --fix-check and --net-value go with --review-record (--head also goes with --confirm)", messages,
                      "the usage line changed:\n" + err)

    def test_a_grant_on_an_impossible_date_is_a_usage_error(self):
        rc, out, err = self.run_args(*self.granted("--grant", REVIEW_GRANT))  # the sibling: a real date passes
        self.assertEqual(rc, 0, "merge refused the good --grant:\n" + out + err)
        for date in ("2026-99-99 25:99 CST", "2026-02-30 06:08 CST"):
            with self.subTest(date=date):
                out, _err = self.assert_usage_error(*self.granted("--grant", grant_text(cite=f"item 396 a, owner, {date}")))
                self.assertNotIn(tm.REVIEW_MARKER, out)



if __name__ == "__main__":
    unittest.main()
