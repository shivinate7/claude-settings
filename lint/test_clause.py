"""Unit cases for lint/_clause.py, the clause parser the cannot-claim check reads.

The contract these cases pin (the builder implements it):
- sentences(text, mask) -> [(start, end)]. A sentence ends after . ! ? that a space or the end follows, at a position
  the mask leaves unmarked. Each span keeps its terminator.
- clauses(sentence, mask) -> [Clause]. A clause ends at ; : ! ? a dash or a comma, and before a comma and a conjunction.
  A clause also starts at `because`. start and end are offsets into the sentence and exclude the terminator.
- mask: one bool per character, True inside a code span or a quote. The caller builds it. The parser reads no quotes.
- Clause fields: start, end, join, subject, verb, aux, modal, negated, conditional, tense, passive, object, complement,
  reason_for, lead, term, hard_end, sent_end, lead_at, lead_end. Words are lowercase. join is the word that opens the
  clause, or None.
- Lexicons: NEGATORS, ADVERBS, CONDITIONALS, REASON_LINKS, DETERMINERS, CANNOT_FORMS.

Sentences marked "constructed" are not in test_report_guard_cannot.py. The others are from it.
"""
import importlib.util
import os
import re
import sys
import unittest

import _clause as clause
import report_guard

REPORT_GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_guard.py")


def none(text):
    return [False] * len(text)


def code_mask(text):
    """True inside each `code span`, the mask the check passes in."""
    mask = none(text)
    for m in re.finditer(r"`[^`]*`", text):
        mask[m.start():m.end()] = [True] * (m.end() - m.start())
    return mask


def parse(sentence):
    return clause.clauses(sentence, none(sentence))


def calls_of(fn):
    """The Python and C calls fn makes, counted by sys.setprofile. The count does not depend on the clock."""
    count = [0]

    def probe(frame, event, arg):
        if event in ("call", "c_call"):
            count[0] += 1

    sys.setprofile(probe)
    try:
        fn()
    finally:
        sys.setprofile(None)
    return count[0]


class SentenceTests(unittest.TestCase):
    def split(self, text, mask=None):
        spans = clause.sentences(text, none(text) if mask is None else mask)
        return [text[start:end].strip() for start, end in spans]

    def test_a_terminator_ends_a_sentence_and_stays_in_it(self):
        # Catches: a span that drops its terminator, or a text that does not split after a period.
        self.assertEqual(self.split("I can't merge PR 12. The branch is protected."),
                         ["I can't merge PR 12.", "The branch is protected."])

    def test_a_dot_in_a_code_span_ends_no_sentence(self):
        # Catches: the mask ignored, so the dot in `a.b` ends a sentence and one sentence becomes three.
        text = "Run `a.b` now. I can't merge PR 12."
        self.assertEqual(self.split(text, code_mask(text)), ["Run `a.b` now.", "I can't merge PR 12."])

    def test_a_code_span_over_two_lines_masks_its_dots(self):
        # Catches: a multi-line code span whose dot before a line break ends a sentence.
        text = "Run `a.\nb.c` now. I can't push."
        self.assertEqual(self.split(text, code_mask(text)), ["Run `a.\nb.c` now.", "I can't push."])

    def test_a_comment_opener_inside_a_code_span_ends_no_sentence(self):
        # Catches: `//` or `#` inside a code span read as a comment that hides the sentence end after it.
        text = "`//` and `#` are comments. I can't merge PR 12."
        self.assertEqual(self.split(text, code_mask(text)),
                         ["`//` and `#` are comments.", "I can't merge PR 12."])

    def test_a_lone_quote_in_text_does_not_hide_a_sentence_end(self):
        # Catches: a lone double quote read as an open quote, so the parser masks the rest and no sentence ends.
        self.assertEqual(self.split('Say "no. I can\'t merge PR 12.'), ['Say "no.', "I can't merge PR 12."])

    def test_a_dot_inside_a_token_ends_no_sentence(self):
        # Catches: a dot read as a sentence end when no space follows it, as in api.github.com.
        self.assertEqual(self.split("Reach api.github.com today. I can't merge PR 12."),
                         ["Reach api.github.com today.", "I can't merge PR 12."])

    def test_text_with_no_terminator_is_one_span(self):
        # Catches: a text with no terminator that yields no span at all.
        self.assertEqual(self.split("I can't merge PR 12"), ["I can't merge PR 12"])

    def test_empty_text_has_no_sentence(self):
        # Catches: an empty text that yields a span at offset zero.
        self.assertEqual(clause.sentences("", []), [])


class ClauseFieldTests(unittest.TestCase):
    def only(self, sentence):
        found = parse(sentence)
        self.assertEqual(len(found), 1, "one clause wanted, %d found: %r" % (len(found), sentence))
        return found[0]

    def test_start_and_end_bound_the_clause_without_its_terminator(self):
        # Catches: end one past the period, so the clause text carries its terminator.
        sentence = "I can't merge PR 12."
        found = self.only(sentence)
        self.assertEqual(sentence[found.start:found.end], "I can't merge PR 12", "start/end: the clause text is wrong")

    def test_a_semicolon_and_a_comma_before_but_end_a_clause(self):
        # Catches: no split at a semicolon, or no split at a comma before a conjunction.
        self.assertEqual(len(parse("I could not open the PR; open it from your computer.")), 2,
                         "clauses: no split at the semicolon")
        self.assertEqual(len(parse("I can't merge PR 12, but the CI is red.")), 2,
                         "clauses: no split at the comma before but")

    def test_join_is_the_word_that_opens_a_clause(self):
        # Catches: join always None, so the word that opens a later clause is lost.
        found = parse("I can't merge PR 12, but the CI is red.")
        self.assertIsNone(found[0].join, "join: the first clause has an opener")
        self.assertEqual(found[1].join, "but", "join: the second clause does not open with but")

    def test_subject_is_the_head_and_a_possessive_gives_its_possessor(self):
        # Catches: the head noun of the phrase ("check") taken in place of the possessor ("main").
        found = parse("Main's check blocks PR 12, so I can't merge it.")
        self.assertEqual(len(found), 2, "clauses: no split at the comma before so")
        self.assertEqual(found[0].subject, "main", "subject: a possessive should give main")
        self.assertEqual(found[1].subject, "i", "subject: the second clause's subject is not I")
        self.assertEqual(found[1].join, "so", "join: the second clause does not open with so")

    def test_verb_is_the_lemma_not_the_surface_form(self):
        # Catches: the surface form ("failed") taken where the lemma ("fail") is due.
        for sentence, verb in (("The push failed.", "fail"), ("I can't merge PR 12.", "merge")):
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).verb, verb, "verb: wrong lemma for %r" % sentence)

    def test_a_regular_past_tense_verb_drops_its_ed_and_its_doubled_consonant(self):
        # Catches: the -ed rule negated (checked read as chec), or read for words of four letters or fewer only (checked
        # kept whole). Neither word is in the irregular table, so only the rule reads them.
        for sentence, verb in (("I checked the CI.", "check"), ("The job dropped.", "drop")):
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).verb, verb, "verb: wrong lemma for %r" % sentence)

    def test_a_clause_that_ends_on_a_be_word_reads_be_as_its_verb(self):
        # Catches: the copula branch skipped when no verb word follows the be word, so the verb reads None.
        for sentence in ("I am.", "The check was."):
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).verb, "be",
                                 "verb: a clause that ends on a be word has no verb for %r" % sentence)

    def test_aux_is_the_auxiliary_without_its_negation(self):
        # Catches: aux always None, so the auxiliary of a negated verb group is lost.
        for sentence, aux in (("I can't merge PR 12.", "can"), ("I could not open the PR.", "could")):
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).aux, aux, "aux: wrong auxiliary for %r" % sentence)

    def test_modal_is_cannot_can_would_or_plain(self):
        # Catches: every modal read as plain. The could-reads-as-plain row is an assumption the commit message flags.
        cases = (("I can't merge PR 12.", "cannot"), ("I can’t merge PR 12.", "cannot"),
                 ("I can merge PR 12.", "can"), ("I would not merge PR 12.", "would"),
                 ("I will merge PR 12.", "plain"), ("I could not push.", "plain"))
        for sentence, modal in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).modal, modal, "modal: wrong value for %r" % sentence)

    def test_negated_is_true_for_a_negator_and_the_cannot_forms(self):
        # Catches: negated always False, so a negated claim reads as an affirmed one.
        cases = (("I never merged PR 12.", True), ("I merged PR 12.", False), ("I can't merge PR 12.", True),
                 ("I cannot push.", True), ("I can merge PR 12.", False))
        for sentence, negated in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).negated, negated, "negated: wrong value for %r" % sentence)

    def test_conditional_is_the_clause_that_holds_if_unless_whether_or_would(self):
        # Catches: conditional always False, so an if-clause reads as a plain statement.
        found = parse("If the branch is protected, I can't merge PR 12.")
        self.assertEqual(len(found), 2, "clauses: no split at the comma")
        self.assertTrue(found[0].conditional, "conditional: the if clause is not conditional")
        self.assertFalse(found[1].conditional, "conditional: the main clause is conditional")

    def test_tense_is_past_present_or_future(self):
        # Catches: tense always present, so a past refusal reads as a present one.
        cases = (("I could not push the branch.", "past"), ("I can't merge PR 12.", "present"),
                 ("I will not merge PR 12.", "future"))
        for sentence, tense in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).tense, tense, "tense: wrong value for %r" % sentence)

    def test_passive_is_true_for_a_be_participle_in_a_passive_sense(self):
        # Catches: passive always False, so a passive merge reads as an active one.
        cases = (("PR 12 was merged by the bot.", True), ("I merged PR 12.", False))
        for sentence, passive in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).passive, passive, "passive: wrong value for %r" % sentence)

    def test_object_is_the_head_noun_before_the_first_preposition_with_numbers_skipped(self):
        # Catches: the last noun of the clause ("main", "word") or a number ("12") taken as the object.
        cases = (("I can't open the PR without your word.", "pr"), ("I can't merge PR 12 into main.", "pr"),
                 ("I cannot push.", None))
        for sentence, obj in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).object, obj, "object: wrong head for %r" % sentence)

    def test_complement_is_the_predicate_adjective_after_a_copula(self):
        # Catches: complement always None, so a predicate adjective ("red") is lost.
        cases = (("The check is red.", "red"), ("I can't merge PR 12.", None))
        for sentence, complement in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual(self.only(sentence).complement, complement,
                                 "complement: wrong value for %r" % sentence)

    def test_reason_for_is_the_reason_link_in_its_clause(self):
        # Catches: reason_for always None, so the because-clause that gives the reason is not marked.
        found = parse("I can't merge PR 12 because the branch is protected.")
        self.assertEqual(len(found), 2, "clauses: no split at because")
        self.assertIsNone(found[0].reason_for, "reason_for: the claim clause names a reason link")
        self.assertEqual(found[1].reason_for, "because", "reason_for: the reason clause names no link")
        self.assertEqual(found[1].join, "because", "join: the reason clause does not open with because")


class SeparatorFieldTests(unittest.TestCase):
    """The fields that place a clause among its separators and stops. Each is named here, so no field of Clause is untested."""

    def test_lead_is_the_separator_before_the_clause_and_empty_for_the_first(self):
        # Catches: lead always "", so the comma, semicolon or dash that opens a later clause is lost.
        cases = (("I can't merge PR 12, but the CI is red.", ["", ","]),
                 ("I can't merge PR 12; the CI is red.", ["", ";"]),
                 ("I can't merge PR 12 -- the CI is red.", ["", "--"]))
        for sentence, leads in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual([c.lead for c in parse(sentence)], leads,
                                 "lead: wrong separator before a clause in %r" % sentence)

    def test_term_is_the_separator_after_the_clause_and_the_period_closes_the_last(self):
        # Catches: term always "", so the comma, semicolon or period that closes a clause is lost. A sentence with no
        # terminator closes its last clause with nothing.
        cases = (("I can't merge PR 12, but the CI is red.", [",", "."]),
                 ("I can't merge PR 12; the CI is red.", [";", "."]),
                 ("I can't merge PR 12", [""]))
        for sentence, terms in cases:
            with self.subTest(sentence=sentence):
                self.assertEqual([c.term for c in parse(sentence)], terms,
                                 "term: wrong separator after a clause in %r" % sentence)

    def test_lead_at_is_where_the_separator_before_the_clause_starts(self):
        # Catches: lead_at always 0, so the place of the separator is lost. The first clause has no separator, so its
        # offset is 0.
        sentence = "Run it; I can't merge PR 12."
        found = parse(sentence)
        self.assertEqual(found[0].lead_at, 0, "lead_at: the first clause has no separator, so its offset is not 0")
        self.assertEqual(found[1].lead_at, sentence.index(";"), "lead_at: the separator before the second clause starts elsewhere")

    def test_lead_end_is_where_the_separator_before_the_clause_ends(self):
        # Catches: lead_end always 0 or equal to lead_at, so the width of the separator is lost. A one-character mark ends
        # one past where it starts.
        sentence = "Run it; I can't merge PR 12."
        found = parse(sentence)
        self.assertEqual(found[0].lead_end, 0, "lead_end: the first clause has no separator, so its offset is not 0")
        self.assertEqual(found[1].lead_end, sentence.index(";") + 1,
                         "lead_end: the separator before the second clause ends elsewhere")

    def test_lead_end_after_a_masked_span_is_the_later_separator(self):
        # Catches: a masked span between two separators. The later separator is dropped (`elif sep and not lead`), so the
        # clause after it keeps the earlier separator's lead_end. The span is the code span `not connected`.
        sentence = "MCP status: `not connected`; I cannot open a PR."
        found = clause.clauses(sentence, code_mask(sentence))
        self.assertEqual(len(found), 2, "two clauses wanted, %d found" % len(found))
        self.assertEqual(found[1].lead_end, sentence.index(";") + 1,
                         "lead_end: the separator before the claim ends at the colon, not at the later semicolon")

    def test_hard_end_is_the_nearest_hard_stop_at_or_after_the_clause_start(self):
        # Catches: hard_end always the sentence end, or a comma or a dot inside a token read as the hard stop. The comma is
        # no hard stop, so the first clause ends at the semicolon; api.github.com has no hard stop, so its clause ends at
        # the period.
        sentence = "I can't merge PR 12, but the CI is red; I wait."
        self.assertEqual([c.hard_end for c in parse(sentence)],
                         [sentence.index(";"), sentence.index(";"), sentence.rindex(".")],
                         "hard_end: wrong hard stop for a clause in %r" % sentence)
        sentence = "Reach api.github.com today, I can't merge PR 12."
        self.assertEqual(parse(sentence)[0].hard_end, sentence.rindex("."),
                         "hard_end: a dot inside a token is read as a hard stop")

    def test_hard_end_is_the_text_end_when_no_hard_stop_follows(self):
        # Catches: hard_end read past the text, or the stop taken from another clause. With no stop after the clause,
        # hard_end is the length of the sentence.
        sentence = "I can't merge PR 12"
        self.assertEqual(parse(sentence)[0].hard_end, len(sentence), "hard_end: no stop follows the clause")

    def test_sent_end_is_the_nearest_sentence_stop_and_a_dot_inside_a_token_counts(self):
        # Catches: sent_end read from the hard stops only, so the dot inside api.github.com is skipped and the clause runs to
        # the period at the end of the sentence.
        sentence = "Reach api.github.com today, I can't merge PR 12."
        self.assertEqual(parse(sentence)[0].sent_end, sentence.index("api.") + len("api"),
                         "sent_end: the dot inside api.github.com is not the nearest stop")

    def test_sent_end_is_the_text_end_when_no_stop_follows(self):
        # Catches: sent_end read past the text. With no sentence stop after the clause, sent_end is the length of the sentence.
        sentence = "I can't merge PR 12"
        self.assertEqual(parse(sentence)[0].sent_end, len(sentence), "sent_end: no stop follows the clause")


class LexiconTests(unittest.TestCase):
    def test_negators_are_the_negation_words(self):
        # Catches: a negation word dropped from NEGATORS, or a non-negator added to it.
        self.assertEqual(set(clause.NEGATORS), {"not", "n't", "never", "no"}, "NEGATORS")

    def test_adverbs_are_the_one_adverb_list_of_the_check(self):
        # Catches: an adverb dropped from ADVERBS.
        words = {"even", "yet", "currently", "actually", "really", "still", "also", "just", "now", "directly",
                 "simply", "unfortunately"}
        self.assertEqual(set(clause.ADVERBS), words, "ADVERBS")

    def test_writer_pattern_is_built_from_the_one_adverb_pattern(self):
        # Catches: the check's writer pattern built from its own adverb list rather than from ADVERB_PATTERN, so an -ly
        # adverb outside the list ("temporarily") is not written by the writer.
        self.assertIn(clause.ADVERB_PATTERN, report_guard.CANNOT_WRITER_RE.pattern,
                      "the writer pattern is not built from ADVERB_PATTERN")

    def fresh_report_guard(self, name, words):
        """A fresh load of lint/report_guard.py while _clause.<name> holds `words`. The probe is not in sys.modules, so the
        shared report_guard is not touched, and the list is set back when the case ends."""
        original = getattr(clause, name)
        setattr(clause, name, words)
        self.addCleanup(setattr, clause, name, original)
        spec = importlib.util.spec_from_file_location("report_guard_lexicon_probe", REPORT_GUARD)
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        return probe

    def test_preposition_pattern_is_built_from_the_shared_preposition_list(self):
        # Catches: _PREPOSITION held as a literal copy of PREPOSITIONS, so a preposition added to the shared list never ends
        # a pr-open object, and the copy stays the same when the list changes.
        probe = self.fresh_report_guard("PREPOSITIONS", ("zqxvprep",))
        self.assertEqual(probe._clause.PREPOSITIONS, ("zqxvprep",), "scope: the probe does not read the sentinel list")
        self.assertNotIn("zqxvprep", report_guard._PREPOSITION, "control: the shared report_guard reads the sentinel")
        self.assertIn("zqxvprep", probe._PREPOSITION, "_PREPOSITION is not built from _clause.PREPOSITIONS")

    def test_fail_end_is_built_from_the_shared_outage_verbs(self):
        # Catches: _FAIL_END held as a literal copy of OUTAGE_VERBS, so a verb added to the shared list does not stop
        # "failing to <verb>" from reading as an outage rather than a red check.
        probe = self.fresh_report_guard("OUTAGE_VERBS", ("zqxvverb",))
        self.assertEqual(probe._clause.OUTAGE_VERBS, ("zqxvverb",), "scope: the probe does not read the sentinel list")
        self.assertNotIn("zqxvverb", report_guard._FAIL_END, "control: the shared report_guard reads the sentinel")
        self.assertIn("zqxvverb", probe._FAIL_END, "_FAIL_END is not built from _clause.OUTAGE_VERBS")

    def test_ci_checks_is_built_from_the_shared_outage_nouns(self):
        # Catches: _CI_CHECKS held as a literal copy of OUTAGE_NOUNS, so a noun added to the shared list does not make
        # "<noun> checks" read as an outage rather than a red CI check.
        probe = self.fresh_report_guard("OUTAGE_NOUNS", ("zqxvnoun",))
        self.assertEqual(probe._clause.OUTAGE_NOUNS, ("zqxvnoun",), "scope: the probe does not read the sentinel list")
        self.assertNotIn("zqxvnoun", report_guard._CI_CHECKS, "control: the shared report_guard reads the sentinel")
        self.assertIn("zqxvnoun", probe._CI_CHECKS, "_CI_CHECKS is not built from _clause.OUTAGE_NOUNS")

    def test_report_guard_keeps_no_cant_of_its_own(self):
        # Catches: _CANT, a copy of the can't forms that the hand-off cite reads, kept in report_guard beside the shared
        # CANNOT_FORMS, so a form added to one list does not reach the other.
        self.assertFalse(hasattr(report_guard, "_CANT"), "report_guard keeps its own _CANT, a copy of the can't forms")

    def test_capability_re_is_built_from_the_shared_cant_forms(self):
        # Catches: CAPABILITY_RE built from its own copy of the can't forms, so a form added to _clause.CANT_FORMS does not
        # read as a capability.
        self.assertTrue(hasattr(clause, "CANT_FORMS"), "_clause has no CANT_FORMS, so the can't forms have no home")
        probe = self.fresh_report_guard("CANT_FORMS", ("zqxvform",))
        self.assertEqual(probe._clause.CANT_FORMS, ("zqxvform",), "scope: the probe does not read the sentinel list")
        self.assertNotIn("zqxvform", report_guard.CAPABILITY_RE.pattern, "control: the shared report_guard reads the sentinel")
        self.assertIn("zqxvform", probe.CAPABILITY_RE.pattern, "CAPABILITY_RE is not built from _clause.CANT_FORMS")

    def test_cannot_forms_begins_with_the_cant_forms(self):
        # Catches: CANNOT_FORMS built without the can't forms first, so the claim check and the hand-off cite read the start of
        # the phrases from two lists.
        self.assertTrue(hasattr(clause, "CANT_FORMS"), "_clause has no CANT_FORMS, so the can't forms have no home")
        self.assertEqual(clause.CANNOT_FORMS[:len(clause.CANT_FORMS)], clause.CANT_FORMS,
                         "CANNOT_FORMS does not begin with CANT_FORMS")

    def test_conditionals_are_the_words_that_make_a_clause_conditional(self):
        # Catches: a conditional word dropped from CONDITIONALS.
        self.assertEqual(set(clause.CONDITIONALS), {"if", "unless", "whether", "would"}, "CONDITIONALS")

    def test_reason_links_are_the_words_that_open_a_reason(self):
        # Catches: REASON_LINKS holding a word the check does not read as a reason, or missing because.
        self.assertEqual(set(clause.REASON_LINKS), {"because"}, "REASON_LINKS")

    def test_determiners_are_the_words_a_noun_phrase_opens_with(self):
        # Catches: a determiner dropped from DETERMINERS, so a noun phrase starting with it loses its head.
        words = {"a", "an", "the", "this", "that", "these", "those", "its", "their", "his", "her", "our", "my", "your"}
        self.assertEqual(set(clause.DETERMINERS), words, "DETERMINERS")

    def test_cannot_forms_hold_the_basic_forms(self):
        # Catches: a basic cannot form ("can't", "could not", "unable to") dropped from CANNOT_FORMS. The check also
        # has longer forms ("not able to", "no way to"); this case pins the basic six only.
        basic = {"can't", "cannot", "unable to", "can not", "could not", "couldn't"}
        self.assertLessEqual(basic, set(clause.CANNOT_FORMS), "CANNOT_FORMS lacks a basic form")


class ReasonTests(unittest.TestCase):
    def test_reasons_return_the_text_after_each_reason_link(self):
        # Catches: each reason event skipped as overlapping the last one found (the `at < done` test inverted), so one
        # reason is lost, or every reason is lost. Each reason runs to the next hard stop.
        self.assertEqual(clause.reasons("I was merging PR 12 because the branch is protected."), ["the branch is protected"],
                         "reasons: one because clause gives no reason")
        self.assertEqual(clause.reasons("I can't merge PR 12 because the branch is protected. Also because the CI is red."),
                         ["the branch is protected", "the CI is red"], "reasons: the second sentence's reason is lost")


class IsReasonTests(unittest.TestCase):
    def test_a_weren_t_form_is_a_verb_of_a_reason(self):
        # Catches: "weren't" missing from VERBS, so "the tests weren't green" reads as no reason while "aren't green" reads as
        # one. The curly apostrophe reads the same.
        self.assertTrue(clause.is_reason("the tests weren't green"), "is_reason: weren't is not a verb")
        self.assertTrue(clause.is_reason("the tests weren’t green"), "is_reason: curly weren’t is not a verb")

    def test_an_aren_t_form_stays_a_verb_and_a_noun_phrase_stays_no_reason(self):
        # Control: aren't is a verb already, and "a protected branch" holds no verb, since a determiner makes protected an
        # adjective.
        self.assertTrue(clause.is_reason("the tests aren't green"), "is_reason: aren't is not a verb")
        self.assertFalse(clause.is_reason("a protected branch"), "is_reason: a noun phrase reads as a reason")


class LinearTests(unittest.TestCase):
    def test_work_grows_linearly_with_the_clause_count(self):
        # Catches: a rescan of the earlier clauses at each new clause, whose work grows as the square of the count.
        def text(k):
            return "I can't merge PR 12, but the CI is red, " * k + "so I can't merge it"

        small, big = text(40), text(160)
        self.assertGreater(len(parse(small)), 40, "the probe sentence does not split into clauses")

        def work(sentence):
            mask = none(sentence)
            return calls_of(lambda: (clause.sentences(sentence, mask), clause.clauses(sentence, mask)))

        small_calls = work(small)
        self.assertGreater(small_calls, 0, "the probe counted no calls")
        ratio = work(big) / small_calls
        self.assertLess(ratio, 6, "work grew %.1fx for 4x the clauses; linear is near 4x, quadratic near 16x" % ratio)


if __name__ == "__main__":
    unittest.main()
