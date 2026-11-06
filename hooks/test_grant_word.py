#!/usr/bin/env python3
"""Cases for the spawn grant word (hooks/grant_word.py, the one home of the word's form).

    python3 -m pytest hooks/test_grant_word.py -q

The word is `grant <slug> spawn <n>m|h` or `grant off <slug>`. The whole prompt, in any case, with surrounding
whitespace ignored. Any other text grants nothing. The parser is assumed to be `parse(text)`, returning
(act, slug, seconds) for a grant (seconds None for `off`), or None when the text grants nothing.

Each case that says a text grants nothing runs beside a control: a valid word the parser must read. A
missing parser reads every text as nothing, so the negative alone would pass there. The control is what
makes that case red on a tree with no parser, and the failure names it.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import grant_word
except ImportError:  # not built yet: each case then fails on its own assert, never on this import
    grant_word = None

SPAWN_10M = ("spawn", "icon-a", 600)
GRANT_10M = "grant icon-a spawn 10m"


def read(text):
    """What the parser reads `text` as, or None. None while the parser is not built."""
    return None if grant_word is None else grant_word.parse(text)


def expect_reads(text, want, cause):
    got = read(text)
    assert got == want, "%s: %r read as %r, want %r" % (cause, text, got, want)


def expect_nothing(text, control, cause, want=SPAWN_10M):
    """`control` must read as `want` first, so a missing parser cannot pass this case."""
    expect_reads(control, want, "control, a valid word is not read")
    got = read(text)
    assert got is None, "%s: %r read as %r, want no grant" % (cause, text, got)


def test_minutes_form_reads_as_a_spawn_grant_in_seconds():
    expect_reads(GRANT_10M, SPAWN_10M, "the minutes form")


def test_hours_form_reads_in_seconds():
    expect_reads("grant icon-a spawn 2h", ("spawn", "icon-a", 7200), "the hours form")


def test_keywords_read_in_any_case():
    expect_reads("Grant icon-a Spawn 10M", SPAWN_10M, "mixed-case keywords and unit")
    expect_reads("GRANT icon-a SPAWN 2H", ("spawn", "icon-a", 7200), "upper-case keywords and unit")


def test_surrounding_whitespace_is_ignored():
    expect_reads("  \t" + GRANT_10M + " \n", SPAWN_10M, "surrounding spaces, a tab and a newline")


def test_bare_number_grants_nothing():
    expect_nothing("grant icon-a spawn 10", GRANT_10M, "a length with no unit")


@pytest.mark.parametrize("text", ["grant icon-a spawn 0m", "grant icon-a spawn -5m"])
def test_length_must_be_a_positive_integer(text):
    expect_nothing(text, GRANT_10M, "a length that is not a positive integer")


@pytest.mark.parametrize("text", [
    "please grant icon-a spawn 10m",
    "grant icon-a spawn 10m thanks",
    "grant icon-a spawn 10m\nthanks",
])
def test_extra_text_grants_nothing(text):
    expect_nothing(text, GRANT_10M, "extra text around the word")


def test_another_verb_grants_nothing():
    expect_nothing("grant icon-a build 10m", GRANT_10M, "a verb other than spawn")


def test_grant_off_reads_as_an_end_of_the_slugs_grant():
    expect_reads("grant off icon-a", ("off", "icon-a", None), "grant off")
    expect_reads("GRANT OFF icon-a", ("off", "icon-a", None), "grant off in upper case")


@pytest.mark.parametrize("text", ["grant off icon-a 10m", "grant off -icon"])
def test_grant_off_takes_a_slug_and_nothing_else(text):
    expect_nothing(text, "grant off icon-a", "grant off with a length or a bad slug", want=("off", "icon-a", None))


@pytest.mark.parametrize("text", [
    "grant -icon spawn 10m",
    "grant _icon spawn 10m",
    "grant icon.a spawn 10m",
    "grant icon_a!x spawn 10m",
    "grant spawn 10m",
])
def test_bad_or_missing_slug_grants_nothing(text):
    expect_nothing(text, GRANT_10M, "a slug that breaks the form, or no slug")


def test_slug_length_limit_is_32_characters():
    longest = "a" + "b" * 31
    control = "grant %s spawn 10m" % longest
    expect_nothing("grant %s spawn 10m" % ("a" * 33), control, "a 33-character slug",
                   want=("spawn", longest, 600))


def test_acts_constant_names_the_spawn_tools_once():
    got = getattr(grant_word, "ACTS", None)
    assert got == {"spawn": ("Agent", "Task")}, "the ACTS constant is %r, want the spawn act's two tools" % (got,)
