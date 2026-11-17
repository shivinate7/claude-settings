#!/usr/bin/env python3
"""Every Stop refusal of a reply tells the session to post only the missing or corrected line, never to resend it.

Owner ruling R10 (inbox fb-1544-5, decision guard-remedy-not-to-owner): after any hook refusal of a reply, the session
posts only the short correction and never resends the reply, and every refusal text says so. The breach it stops:
the Departs-from and Recovered refusals named only what was missing, so the session resent the whole report.

The table is the refusal fixtures of lint/test_report_guard_remedy.py (its FIXTURES tuple, one home). Each runs through
report_guard as the Stop hook, through that suite's refusal_for(). The printed reason must tell the session to post only
the missing or corrected line and not to resend the reply, and it must carry the one shared correction tail,
report_guard.CORRECTION_TAIL. A refusal that builds its own text fails the second assert.

Not run one by one: the Unvetted "the check failed" text (only an exception reaches it), and the departs and hand-off
misses the remedy suite does not fixture. Each of those reaches the Stop join, where the reasons are joined, so the
fixtures of its check cover the join.

Controls pin the wording detector on fixed sentences, so a detector that flags nothing cannot pass the table.

Run it as:

    python3 lint/test_report_guard_correction.py -v
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
import report_guard as RG  # noqa: E402  the one home of the shared correction tail, CORRECTION_TAIL
import test_report_guard_remedy as trr  # noqa: E402  the refusal fixtures and the Stop runner (one home)

# The ruling's wording: post only the missing or corrected line, and never resend the reply.
POST_ONLY = re.compile(r"\bpost only\b", re.IGNORECASE)
MISSING_OR_CORRECTED = re.compile(r"\b(?:missing|corrected|correction)\b", re.IGNORECASE)
NO_RESEND = re.compile(r"\b(?:never|do not|don't)\s+(?:re-?send|send|write|repeat|post)\b[^.;]*?\b(?:reply|report)\b",
                       re.IGNORECASE)


def tells_correction_only(text):
    """True when `text` holds all three parts: post only, the missing or corrected line, and a negated resend."""
    return bool(POST_ONLY.search(text) and MISSING_OR_CORRECTED.search(text) and NO_RESEND.search(text))


def setUpModule():
    trr.setUpModule()  # the config isolation, the model stub and the run folder, as the remedy suite sets them


def tearDownModule():
    trr.tearDownModule()


class CorrectionTailTable(unittest.TestCase):
    def setUp(self):
        # A RemedyReasons instance only supplies its fixtures and Stop runner; its own test methods do not run here.
        self.helper = trr.RemedyReasons("test_2_clean_report_is_not_blocked")

    def test_every_stop_refusal_of_a_reply_says_post_only_the_correction(self):
        tail = getattr(RG, "CORRECTION_TAIL", "")
        for name in trr.FIXTURES:
            with self.subTest(refusal=name):
                reason, _ = self.helper.refusal_for(name)  # asserts the refusal fires
                self.assertTrue(tells_correction_only(reason),
                                "refusal %s does not tell the session to post only the missing or corrected line "
                                "and never resend the reply: %r" % (name, reason))
                self.assertTrue(tail, "report_guard holds no shared CORRECTION_TAIL constant")
                self.assertIn(tail, reason,
                              "refusal %s builds its text without the shared CORRECTION_TAIL: %r" % (name, reason))


class CorrectionTailControls(unittest.TestCase):
    # Green on the old code: they test the detector on fixed sentences, not on report_guard.
    def test_control_wording_detector_reads_the_ruling(self):
        ruling_wording = "Post only the missing or corrected line, as a short follow-up. Never send the reply again."
        fact_only = "Report-shape guard: this turn landed a commit, and the reply does not end with the report."
        no_post_only = "Never send the reply again; add the missing line."
        resend_allowed = "Post only the corrected line; send the reply again."
        self.assertTrue(tells_correction_only(ruling_wording), "control: the ruling's wording is not read")
        self.assertFalse(tells_correction_only(fact_only), "control: a fact-only refusal reads as the ruling")
        self.assertFalse(tells_correction_only(no_post_only), "control: a text with no 'post only' reads as the ruling")
        self.assertFalse(tells_correction_only(resend_allowed), "control: a text that allows a resend reads as the ruling")


if __name__ == "__main__":
    unittest.main()
