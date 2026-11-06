"""The spawn grant word: the one home of its form (decision grant-reaches-lanes).

The owner types `grant <slug> spawn <n>m|h` in the coordinator, or `grant off <slug>`. The word is the whole
prompt, in any case, with surrounding whitespace ignored. Any other text grants nothing.
hooks/local_time.py reads the word to print the relay line, and hooks/guard.py reads it to judge a lane's spawn.

parse(text) returns (act, slug, seconds), or None. `seconds` is None for `off`, whose act is "off".
"""
import re

# The catalogue: each act the word can grant, and the tools it lets through. The guard reads this, never a copy.
ACTS = {"spawn": ("Agent", "Task")}

SLUG = r"[a-z0-9][a-z0-9_-]{0,31}"  # lower case only: a cs-step tag is lower case
UNITS = {"m": 60, "h": 3600}
_GRANT_FORM = r"(?i:grant)[ \t]+(?P<slug>%s)[ \t]+(?i:(?P<act>%s))[ \t]+(?P<n>[0-9]{1,6})(?i:(?P<unit>[mh]))"
_OFF = re.compile(r"(?i:grant)[ \t]+(?i:off)[ \t]+(?P<slug>%s)" % SLUG)


def parse(text):
    """(act, slug, seconds) for a grant word, ("off", slug, None) for `grant off <slug>`, else None."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    found = _OFF.fullmatch(text)
    if found:
        return "off", found.group("slug"), None
    # Built from ACTS on each parse (re caches it), so an act added to ACTS after import still parses.
    found = re.fullmatch(_GRANT_FORM % (SLUG, "|".join(re.escape(act) for act in ACTS)), text)
    if not found or not int(found.group("n")):
        return None
    return found.group("act").lower(), found.group("slug"), int(found.group("n")) * UNITS[found.group("unit").lower()]
