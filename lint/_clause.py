"""The clause parser the cannot-claim check reads: sentences, clauses and the lexicons of their grammar.

`lint/report_guard.py` imports this module, so the check has one copy of its sentence and clause boundaries and one home
for each word list (NEGATORS, ADVERBS, CONDITIONALS, REASON_LINKS, SUBORDINATORS, RELATIVES, LEAD_INS, DETERMINERS, CANT_FORMS, COULD_NOT_FORMS, CANNOT_FORMS, CHECK_WORDS,
STATE_VERBS, OUTAGE_NOUNS, OUTAGE_VERBS, BACK_PATTERN, STATUS_PATTERN, SPEECH_VERBS, CALL_SUBJECTS) and for the words that
name the writer (WRITER_BEFORE_RE, FROM_HERE_RE and the lead-ins and subject words that own_subject reads). The module reads text and
a mask only: no file, no process. Its cost is one regex pass over a sentence and one over each clause, so the work grows
in step with the text.

sentences(text, mask) -> [(start, end)]: the spans tile the text and each keeps its terminator. `mask` holds one bool per
character, True inside a code span or a quote: the parser reads those characters as blanks and reads no quote itself.
clauses(sentence, mask) -> [Clause]: a clause ends at ; : ! ? a dash, a period, a comma, or a but or because, and the word that
opens it (and, but, or, so, yet, then, because) is its `join`. A period ends a clause when whitespace or the end follows it, or
when a determiner or a pronoun follows it ("main.The", "main.I"), or a digit follows a word of letters ("it.2"); a dot inside a
token ends none (Console.WriteLine). `lead` and `term` are the separators before and after it;
`lead_at` and `lead_end` are where the separator before it starts and ends; `hard_end` is where the nearest hard stop (. ; : ! ? a dash) at or
after its start sits, and `sent_end` the nearest of . ; : ! ? (a dot inside a token counts); all are offsets into the
sentence. A clause's other fields are read from its words alone. The helpers below the clauses (conditional,
veil, negated_near, own_subject, past, opens_with, opens_with_joiner, lead_opens_clause, strip_adverbs, reasons, reasons_before, is_reason,
check_word_counts, form_pattern, unopen) read the grammar of the cannot-claim check from the same lexicons.
"""
import bisect
import re
from typing import NamedTuple, Optional

NEGATORS = ("not", "n't", "never", "no")
ADVERBS = ("even", "yet", "currently", "actually", "really", "still", "also", "just", "now", "directly", "simply",
           "unfortunately")
# Any other adverb in -ly ("temporarily", "honestly") is read as an adverb where the grammar allows one: between a subject
# and its verb, after not, and before the act.
ADVERB_PATTERN = "(?:%s|[a-z]{3,}ly)" % "|".join(ADVERBS)
CONDITIONALS = ("if", "unless", "whether", "would")
REASON_LINKS = ("because",)
DETERMINERS = ("a", "an", "the", "this", "that", "these", "those", "its", "their", "his", "her", "our", "my", "your")
JOINERS = ("and", "but", "or", "so", "yet", "then")
SUBORDINATORS = ("since", "as", "while", "although", "though")  # open a clause whose subject follows
RELATIVES = ("which",)  # open a clause whose subject is the noun before them
LEAD_INS = JOINERS + REASON_LINKS + SUBORDINATORS + RELATIVES  # the words lead_opens_clause reads
PREPOSITIONS = ("for", "of", "in", "on", "to", "from", "with", "about", "against", "at", "by", "per")
_BE_NT_FORMS = ("isn't", "aren't", "wasn't", "weren't")  # every be-form with n't
VERBS = ("is", "are", "was", "were", "has", "have", "had", "does", "do", "did", "can", "cannot") + _BE_NT_FORMS + (
    "doesn't", "didn't", "won't", "not", "no", "needs", "requires")
# The phrases that say a session cannot do an act. A form reads the same with n't or not and with a curly apostrophe.
# The generated tail holds the permission forms: "do not have the permission to", with or without "the", does for do, and
# the nouns of _PERMISSION_NOUNS.
_PERMISSION_NOUNS = ("permission", "authorization", "authorisation", "authority", "ability")
# The three present forms the hand-off cite reads as a capability (report_guard.CAPABILITY_RE reads CANT_FORMS and
# COULD_NOT_FORMS). CANNOT_FORMS starts with them.
CANT_FORMS = ("can't", "cannot", "unable to")
# The two past forms the hand-off cite also reads as a capability. They sit in CANNOT_FORMS after "can not", and a form
# added to CANT_FORMS would widen CANNOT_FORMS, so the cite takes them from this list.
COULD_NOT_FORMS = ("could not", "couldn't")
CANNOT_FORMS = CANT_FORMS + ("can not",) + COULD_NOT_FORMS + ("no way to", "no way I can",
                "no way we can", "not able to", "won't be able to", "will not be able to",
                "haven't been able to", "hasn't been able to", "have not been able to", "has not been able to",
                "not allowed to", "not permitted to", "not going to be able to", "not authorized to", "not authorised to",
                "don't have access to", "do not have access to", "doesn't have access to", "does not have access to",
                "lack permission to", "lacks permission to", "blocked from", "forbidden from") + tuple(
    "%s %s" % (be, able)
    for be in _BE_NT_FORMS for able in ("able to", "allowed to", "permitted to", "going to be able to")) + tuple(
    "%s have %s%s to" % (verb, the, noun)
    for verb in ("don't", "do not", "doesn't", "does not") for the in ("", "the ") for noun in _PERMISSION_NOUNS)
# The nouns that make a checks noun an outage, not a CI check ("the network checks are failing"), and the verbs that make
# "failing to <verb>" an outage, not a red check. They live here, a shared lexicon, so each caller reads an outage alike.
OUTAGE_NOUNS = ("connection", "network", "connectivity", "api", "auth", "authentication", "proxy", "health")
OUTAGE_VERBS = ("start", "connect", "run", "load", "reach", "respond", "authenticate", "fetch", "launch", "initialize",
                "initialise", "clone")
# "sent back 403": the verb phrases that say a call answered with a status, and the HTTP status (a 4xx or 5xx that no hyphen
# joins and no unit follows: "450 files" and "a 450-line diff" are sizes). A clause that holds one is a reason.
BACK_FORMS = ("sent", "came", "gave", "given", "comes", "sends", "gives", "come")
BACK_PATTERN = r"(?:%s)\s+back" % "|".join(BACK_FORMS)
SIZE_UNITS = ("lines?", "files?", "words?", "chars?", "commits?", "bytes?", "[km]b", "ms")
STATUS_PATTERN = r"[45]\d\d\b(?![-\w])(?!\s+(?:%s)\b)" % "|".join(SIZE_UNITS)
WINDOW = 6  # words after a phrase, in its clause, that may name the act
NEGATOR_GAP = 3  # words before a phrase that a negator may sit in and still negate it
NEGATOR_GAP_SKIP = ("am",)  # words the gap does not count: "did not say I am not authorized" reaches the first not
# The words that name a call's outcome: a try, or what the call returned. A sentence that holds one names its check, unless
# the writer is its subject ("I tried" names no call).
CHECK_WORDS = ("tried", "ran", "returned", "refused", "denied", "failed", "errored", "rejected", "blocked", "said",
               "returns", "refuses", "denies", "rejects", "blocks", "says", "fails", "errors")
# The verbs of telling: a negator reaches across a new subject after one ("did not say I am not authorized"), and a check word
# among them (said, says) names a call only when a tool, hook, check, command or remote is its subject ("the hook said").
SPEECH_VERBS = ("say", "says", "said", "saying", "claim", "claims", "claimed", "claiming", "mean", "means", "meant",
                "meaning", "write", "writes", "wrote", "written", "writing")
SPEECH_CHECK_WORDS = tuple(word for word in CHECK_WORDS if word in SPEECH_VERBS)
CALL_SUBJECTS = ("tool", "hook", "check", "command", "remote")  # a source of a call's answer, never a person

_STOPS = PREPOSITIONS + ("without", "into", "onto", "over", "under", "through", "via", "than", "as", "like")
_PRONOUNS = ("i", "we", "you", "he", "she", "it", "they", "there", "here")
_CONTRACTED = {"i'm": ("i", "am"), "we're": ("we", "are"), "you're": ("you", "are"), "they're": ("they", "are"),
               "it's": ("it", "is"), "he's": ("he", "is"), "she's": ("she", "is"), "there's": ("there", "is"),
               "i've": ("i", "have"), "we've": ("we", "have"), "i'll": ("i", "will"), "we'll": ("we", "will"),
               "i'd": ("i", "would"), "we'd": ("we", "would")}
_MODALS = ("can", "could", "would", "will", "shall", "should", "may", "might", "must")
_BE = ("is", "are", "was", "were", "be", "been", "being", "am")
STATE_VERBS = _BE + ("remain", "remains", "remained", "stay", "stays", "stayed", "still")  # "is open" is a state, not an act
_HAVE = ("has", "have", "had")
_DO = ("do", "does", "did")
_PAST_AUX = ("could", "did", "was", "were", "had")
_IRREGULAR = {"is": "be", "are": "be", "was": "be", "were": "be", "been": "be", "being": "be", "am": "be",
              "has": "have", "had": "have", "does": "do", "did": "do", "done": "do", "made": "make", "taken": "take",
              "given": "give", "written": "write", "merged": "merge", "closed": "close", "created": "create",
              "raised": "raise", "filed": "file", "updated": "update", "opened": "open", "pushed": "push",
              "edited": "edit", "marked": "mark", "submitted": "submit", "commented": "comment", "failed": "fail",
              "blocked": "block", "refused": "refuse", "denied": "deny", "declined": "decline"}
_UNDOUBLE = "bdgmnprt"


def _lemma(word):
    """The base form of a verb word: failed -> fail, blocks -> block, merged -> merge."""
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    if len(word) > 4 and word.endswith("ed"):
        stem = word[:-2]
        if stem.endswith("i"):
            return stem[:-1] + "y"
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] in _UNDOUBLE:
            return stem[:-1]
        return stem
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 2 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


_WORD = re.compile(r"\w+(?:['’]\w+)*(?:-\w+)*")
# A period ends a clause when whitespace or the end follows it. A glued period ends one when a determiner or a pronoun follows
# it and a space or an apostrophe follows the word ("main.The failure", "`main`.I think"), or a digit follows a token of
# letters only ("it.2"). A dot inside a token (report_guard.py, v1.2, api.github.com, Console.WriteLine, error.log.1, re.I)
# ends none. "I" counts only as a capital, and no other one-letter word counts, so libfoo.a and foo.i end none.
_AFTER_DOT = "|".join([w for w in DETERMINERS + _PRONOUNS if len(w) > 1] + ["(?-i:I)"])
_LETTERS_ONLY = "|".join(r"(?<=[^\W\d_]{%d})(?<![\w.][^\W\d_]{%d})" % (n, n) for n in range(1, 13))
_PERIOD = r"\.(?!\w)|\.(?=(?:%s)[\s'’])|(?:%s)\.(?=\d)" % (_AFTER_DOT, _LETTERS_ONLY)
_BOUND = re.compile(r"(\s-{1,2}\s)|([;:!?—–]|%s)|(,)|\b(but|because)\b" % _PERIOD, re.I)
_STOP_ANY = re.compile(r"[.;:!?]")
_REASON_STOP = re.compile(r"[;:!?]|%s" % _PERIOD)  # a dot inside a token (package.json) ends no reason
_OPEN_ADJ = re.compile(r"\b((?:%s)\s+(?:\w+ly\s+)*)open\b" % "|".join(STATE_VERBS + DETERMINERS), re.I)
_SENTENCE_GAP = re.compile(r"(?<=[.!?])\s+")


class Clause(NamedTuple):
    start: int
    end: int
    join: Optional[str]
    subject: Optional[str]
    verb: Optional[str]
    aux: Optional[str]
    modal: str
    negated: bool
    conditional: bool
    tense: str
    passive: bool
    object: Optional[str]
    complement: Optional[str]
    reason_for: Optional[str]
    lead: str
    term: str
    hard_end: int
    sent_end: int
    lead_at: int
    lead_end: int


def words(text):
    """The lowercase words of `text`, with a curly apostrophe read as a straight one."""
    return [w.lower().replace("’", "'") for w in _WORD.findall(text)]


def _shadow(text, mask):
    return "".join(" " if hidden else char for char, hidden in zip(text, mask)) if any(mask) else text


def sentences(text, mask):
    """[(start, end)] spans that tile `text`: a sentence ends after . ! or ? that whitespace, a masked character or the
    end follows, and the span runs through that whitespace."""
    bounds = [0] + [m.end() for m in _SENTENCE_GAP.finditer(_shadow(text, mask))] + [len(text)]
    return [(a, b) for a, b in zip(bounds, bounds[1:]) if b > a]


_ADV = ADVERB_PATTERN
_COND_RE = re.compile(r"\b(?:%s)\b" % "|".join(CONDITIONALS), re.I)
_NEGATOR_RE = re.compile(r"\b(?:%s)\b|n['’]t\b" % "|".join(w for w in NEGATORS if w.isalpha()), re.I)
# The writer: the one home of its lead-ins and subject words. A joiner, because or a subordinator may open the clause before
# its subject. I and we are the writer wherever they sit just before a phrase; the cloud and this session too, unless a
# preposition (PREPOSITIONS) sits just before them: "The builder in this session is unable to push." is the builder's line.
_WRITER = r"(?:I|we)"
_PLACE = r"(?:the\s+cloud(?:\s+session)?|this\s+session)"
_LEAD = "|".join(JOINERS + REASON_LINKS + SUBORDINATORS)
_LEAD_RE = re.compile(r"^\W*(?:(?:%s)\b\W*)?" % _LEAD, re.I)
_WRITER_START = re.compile(r"^\W*(?:(?:%s)\b\W*)?%s\b" % (_LEAD, _WRITER), re.I)
WRITER_BEFORE_RE = re.compile(r"\b%s(?:\s+%s)*\s+$" % (_WRITER, _ADV), re.I)  # the text ends in the writer: "I just "
FROM_HERE_RE = re.compile(r"\bfrom\s+(?:here|%s)\b" % _PLACE, re.I)
_OWN_RE = re.compile(
    r"(?:^|\b%s(?:\s+(?:am|are|was|were|have|has|had))?|\bI['’]m|\bwe['’]re"
    r"|\bhere|\bthere(?:\s+(?:is|was)|['’]s))" % _WRITER
    + r"(?:\s+" + _ADV + r")*\s*$", re.I)
_PLACE_END_RE = re.compile(r"\b%s(?:\s+(?:is|was))?(?:\s+%s)*\s*$" % (_PLACE, _ADV), re.I)
_PREPOSITION_END_RE = re.compile(r"\b(?:%s)\W*$" % "|".join(PREPOSITIONS), re.I)
_CALL_SUBJECT_RE = re.compile(r"\b(?:%s)s?\s+(?:%s\s+)*$" % ("|".join(CALL_SUBJECTS), _ADV), re.I)
_PAST_RE = re.compile(r"^(?:could|(?:was|were)n['’]t)", re.I)
_WAS_RE = re.compile(r"\b(?:was|were)(?:\s+%s)*\s*$" % _ADV, re.I)
_ADV_LEAD_RE = re.compile(r"^(?:%s\s+)+" % _ADV, re.I)
_FIRST_WORD = re.compile(r"\s*(\w+)")
_BACK_STATUS_RE = re.compile(r"\b(?:%s)\s+(?:a\s+)?%s" % (BACK_PATTERN, STATUS_PATTERN), re.I)
_PAREN_RE = re.compile(r"\(([^()]+)\)")
_REASON_LEADS = (":", ";", ",", "—", "–", "-", "--")


def conditional(text):
    """True when `text` holds a word of CONDITIONALS."""
    return bool(_COND_RE.search(text))


def veil(text, shadow):
    """`text` with each character that `shadow` blanks read as `_`: a masked span keeps its length and its word count, and
    none of its words is a lexicon word. `shadow` is `text` with its masked characters blanked to spaces."""
    return "".join("_" if char != blank else char for char, blank in zip(text, shadow))


def negated_near(text, gap=NEGATOR_GAP):
    """True when a negator (NEGATORS) sits in the last `gap` words of `text` and reaches the end of it. A word of
    NEGATOR_GAP_SKIP (am) takes no slot. A negator reaches no further than a new subject (a pronoun) unless a speech verb
    (SPEECH_VERBS) comes first: "Don't worry I am" is no negation, "did not say I am" is."""
    counted = [w for w in text.split() if w.lower() not in NEGATOR_GAP_SKIP][-gap:]
    return any(_NEGATOR_RE.search(word) and not _new_subject(counted[k + 1:]) for k, word in enumerate(counted))


def _new_subject(words_after):
    """True when a pronoun that is a subject (not here) sits in `words_after` with no speech verb before it."""
    for word in words_after:
        bare = word.strip(".,;:()\"'_").lower().replace("’", "'")
        if bare in SPEECH_VERBS:
            return False
        if any(w in _PRONOUNS and w != "here" for w in _CONTRACTED.get(bare, (bare,))):
            return True
    return False


def first_words(text, count=WINDOW):
    """The first `count` words of `text`, as written, joined by one space."""
    return " ".join(text.split()[:count])


def own_subject(before):
    """True when the words just before a phrase end in the writer's own subject (I, we, here, there is, the cloud, this
    session), with the auxiliary after it and an adverb (ADVERBS) allowed, or hold no subject: the phrase opens its clause.
    A joining word (JOINERS), because or a subordinator (SUBORDINATORS) before the subject is skipped. The cloud and this
    session are no subject after a preposition (PREPOSITIONS): "The builder in this session is" is the builder's subject."""
    text = _LEAD_RE.sub("", before)
    if _OWN_RE.search(text):
        return True
    place = _PLACE_END_RE.search(text)
    return bool(place) and not _PREPOSITION_END_RE.search(text[:place.start()])


def check_word_counts(before, word, writer_counts=False):
    """True when the bare check word `word` (CHECK_WORDS) names a call, `before` being the text just before it. The writer as
    its subject names none ("I tried"), unless `writer_counts`. A speech word (said, says) names one only when a tool, hook,
    check, command or remote is its subject (CALL_SUBJECTS): "the hook said" does, "the owner said" does not."""
    if not writer_counts and WRITER_BEFORE_RE.search(before):
        return False
    return word.lower() not in SPEECH_CHECK_WORDS or bool(_CALL_SUBJECT_RE.search(before))


def past(phrase, before):
    """True when a phrase reports a failure: could not, wasn't or weren't able, or any phrase right after was or were."""
    return bool(_PAST_RE.match(phrase) or _WAS_RE.search(before))


def opens_with(text, word):
    """True when the first word of `text` is `word`."""
    hit = _FIRST_WORD.match(text)
    return bool(hit) and hit.group(1).lower() == word


def opens_with_joiner(text):
    """True when the first word of `text` is a joiner (JOINERS): and, but, or, so, yet, then."""
    hit = _FIRST_WORD.match(text)
    return bool(hit) and hit.group(1).lower() in JOINERS


_SUBJECT_WORDS = _PRONOUNS + DETERMINERS


_NOUN_VERBS = ("exist", "exists", "persist", "remain", "remains", "happen", "happens", "fail", "break")
_NOUN_ADVERBS = ("also", "still")


def _bare_noun(tokens):
    """True when the words after "that" open with a base name (main, master, origin) or a plural noun with no determiner
    (failures, errors) that a form of be or a verb of _NOUN_VERBS follows, also or still allowed between: a complementizer
    ("yet that failures also fail"), not "that test fails". A word of VERBS ("that does"), or in -ss, -us or -is
    ("process", "status", "analysis"), is no plural noun. A word in -s that no such verb follows is a verb ("that breaks
    on", "that fails also on")."""
    word = tokens[0]
    if word in ("main", "master", "origin"):
        return True
    if not word.endswith("s") or word.endswith(("ss", "us", "is")) or word in VERBS:
        return False
    rest = tokens[1:]
    while rest and rest[0] in _NOUN_ADVERBS:
        rest = rest[1:]
    return bool(rest) and (rest[0] in VERBS or rest[0] in _NOUN_VERBS)


def _opens_with_subject(tokens):
    """True when `tokens` open with a pronoun or a determiner. "that" counts only when no pronoun or determiner follows it:
    "that test fails" opens with a subject, "that the failure is" opens with a complementizer."""
    if tokens[:1] == ["that"]:
        return len(tokens) > 1 and tokens[1] not in _SUBJECT_WORDS and not _bare_noun(tokens[1:])
    return bool(tokens) and tokens[0] in _SUBJECT_WORDS


def lead_opens_clause(lead, after):
    """True when the lead-in word `lead` (JOINERS, REASON_LINKS, SUBORDINATORS or RELATIVES) opens a clause of its own, `after`
    being the text of its clause that follows it. Two lead-ins double as other words, so the words after them decide.
    "yet" joins two clauses only when a subject follows it ("yet the failure is"); otherwise it is an adverb ("not yet
    known", "cannot yet say", "no proof yet that"). "as" opens a clause when a pronoun follows it ("as it also fails"), or
    when a verb follows in its words up to the next lead-in ("as the failure seems"); before yet, being or well, or with no
    verb ("confirmed as pre-existing and"), it is no lead-in. Every other lead-in opens a clause."""
    word = lead.lower()
    if word == "yet":
        return _opens_with_subject(words(strip_adverbs(after.lstrip())))
    if word != "as":
        return True
    tokens = words(after)
    if not tokens or tokens[0] in ("yet", "being", "well"):
        return False
    tokens = words(strip_adverbs(after.lstrip()))
    window = tokens[:next((k for k, w in enumerate(tokens) if w in LEAD_INS), len(tokens))]
    return bool(window) and (window[0] in _PRONOUNS or any(_starts_group(w, k) for k, w in enumerate(window) if k))


def strip_adverbs(text):
    """`text` without the adverbs (ADVERBS) that open it."""
    return _ADV_LEAD_RE.sub("", text)


def is_reason(text):
    """True when `text` is a clause of three words or more with a verb (VERBS, or a word in -ed) that no determiner
    just before it makes an adjective: "a protected branch" holds no verb. "sent back 403" (BACK_PATTERN, then a status)
    is a verb of its own."""
    tokens = [w.strip(".,;:()\"'").lower().replace("’", "'") for w in text.split()]
    return len(tokens) >= 3 and bool(_BACK_STATUS_RE.search(text) or any(
        (w in VERBS or re.fullmatch(r"\w+ed", w)) and not (k and tokens[k - 1] in DETERMINERS)
        for k, w in enumerate(tokens)))


def reasons(text):
    """The clauses of `text` that a reason link opens, in order: the text after a : ; , or dash that whitespace follows,
    the text after because, and the words in parentheses. Each runs to the next . ; : ! ? (a dot inside a token, as in package.json, ends none) and a link inside one is part of
    it."""
    events = []
    for c in clauses(text, [False] * len(text)):
        if c.lead in _REASON_LEADS:
            after = c.lead_at + len(c.lead) + (1 if c.lead in ("-", "--") else 0)
            if text[after:after + 1].isspace():
                events.append((c.lead_at, after + len(text[after:]) - len(text[after:].lstrip()), None))
        elif c.join in REASON_LINKS and text[c.start + len(c.join):][:1].isspace():
            after = c.start + len(c.join)
            events.append((c.start, after + len(text[after:]) - len(text[after:].lstrip()), None))
    events.extend((m.start(), m.start(1), m.end(1)) for m in _PAREN_RE.finditer(text))
    found, done = [], 0
    for at, begin, stop in sorted(events, key=lambda e: e[:2]):
        if at < done:
            continue
        if stop is None:
            hit = _REASON_STOP.search(text, begin)
            stop = hit.start() if hit else len(text)
        if stop > begin:
            found.append(text[begin:stop])
            done = stop
    return found


def reasons_before(head):
    """The clauses of `head`, the text of a sentence up to the end of a phrase, that say why before the phrase: each clause
    ahead of the phrase's own that is_reason accepts. A clause with the writer as its subject (I, we: "I tried it"), one that
    conditions, one that a but follows (a contrast: "The branch is protected but I cannot push" gives no reason) and a
    lead-in with no verb ("Sorry") say nothing."""
    parts = clauses(head, [False] * len(head))
    return [head[c.start:c.end] for c, nxt in zip(parts, parts[1:])
            if not c.conditional and nxt.join != "but" and not _WRITER_START.match(head[c.start:c.end])
            and is_reason(head[c.start:c.end])]


def unopen(text):
    """`text` with each `open` that a state verb or a determiner just before it makes an adjective ("PR 12 is open", "the
    open PR") read as underscores of the same length, so no act reads it."""
    return _OPEN_ADJ.sub(lambda m: m.group(1) + "_" * 4, text)


def form_pattern(form):
    """The regex of a CANNOT_FORMS phrase: its words joined by whitespace, either apostrophe, and a gap for adverbs
    (ADVERBS) after not or a word in n't when able, allowed, permitted, going or been follows."""
    parts = form.split()
    out = re.escape(parts[0]).replace("'", "['’]")
    for k in range(1, len(parts)):
        gapped = (parts[k - 1] == "not" or parts[k - 1].endswith("n't")) and parts[k] in (
            "able", "allowed", "permitted", "going", "been", "authorized", "authorised")
        out += (r"\s+(?:%s\s+)*" % _ADV if gapped else r"\s+") + re.escape(parts[k]).replace("'", "['’]")
    return out


def head_objects(tokens, start):
    """[(word, possessive)] of the noun phrase that begins at tokens[start]: the words up to the first preposition, with
    determiners, numbers, adverbs and joiners dropped. A word in 's names its possessor and is marked possessive."""
    found = []
    for word in tokens[start:]:
        if word in _STOPS:
            break
        if word in DETERMINERS or word in JOINERS or word in ADVERBS or word.isdigit():
            continue
        found.append((word[:-2], True) if word.endswith("'s") else (word, False))
    return found


def object_of(text):
    """The head noun of the object that follows the first word of `text`, else None: the last word of its noun phrase."""
    tokens = words(text)
    found = head_objects(tokens, 1)
    return found[-1][0] if found else None


def _expand(tokens):
    out = []
    for word in tokens:
        out.extend(_CONTRACTED.get(word, (word,)))
    return out


def _is_participle(word):
    return (word.endswith("ed") and len(word) > 3) or word in ("done", "made", "taken", "given", "written", "shown")


def _starts_group(word, k):
    """True when `word`, the k-th of a clause with no pronoun subject, ends the subject: it opens the verb group."""
    return (word in _MODALS or word in _BE or word in _HAVE or word in _DO or word in NEGATORS or word.endswith("n't")
            or word == "cannot" or (_is_participle(word) and k > 0)
            or (word.endswith("s") and k > 1 and not word.endswith("'s")))


def _analyse(tokens):
    """The word-level fields of one clause, from its lowercase words."""
    tokens = _expand(tokens)
    if tokens and tokens[0] in JOINERS + REASON_LINKS:
        tokens = tokens[1:]
    n = len(tokens)
    first = 0
    while first < n and tokens[first] in ADVERBS:
        first += 1
    group = None
    if first < n and tokens[first] in _PRONOUNS:
        group = first + 1
    else:
        for k in range(first + 1, n):
            if _starts_group(tokens[k], k):
                group = k
                break
    subject = None
    if group is not None and first < n:
        region = [w for w in tokens[first:group] if w not in DETERMINERS and not w.isdigit()]
        possessive = next((w for w in region if w.endswith("'s")), None)
        subject = possessive[:-2] if possessive else (region[-1] if region else None)
    aux, negated, modal, future, passive = None, False, "plain", False, False
    verb_at, copula = None, False
    k = group if group is not None else (first if first < n else n)
    last_be = None
    while k < n:
        word = tokens[k]
        if word in ADVERBS:
            k += 1
        elif word in ("not", "never", "no"):
            negated = True
            k += 1
        elif word == "cannot" or word.endswith("n't") or word in _MODALS or word in _BE or word in _HAVE or word in _DO:
            if word == "cannot":
                word, negated = "can", True
            elif word.endswith("n't"):
                negated = True
                word = {"ca": "can", "wo": "will", "sha": "shall"}.get(word[:-3], word[:-3])
            if word in _BE:
                last_be = word
            if aux is None and (word in _MODALS or word in _HAVE or word in _DO or word in _BE):
                aux = word
            if word in ("will", "shall"):
                future = True
            k += 1
        else:
            break
    if aux in _BE and k >= n:
        aux = None
    if k < n:
        verb_at = k
    elif last_be is not None:
        copula = True
    if verb_at is not None and last_be is not None and _is_participle(tokens[verb_at]):
        passive = True
    surface = tokens[verb_at] if verb_at is not None else None
    complement = None
    if surface is not None and last_be is not None and not passive:
        complement, surface, verb_at = surface, "be", None
    elif surface is None and copula:
        surface = "be"
    verb = _lemma(surface) if surface else None
    if aux == "can" and negated:
        modal = "cannot"
    elif aux == "can":
        modal = "can"
    elif aux == "would":
        modal = "would"
    if aux in _PAST_AUX or aux is None and last_be in ("was", "were"):
        past = True
    else:
        past = bool(surface) and (surface.endswith("ed") or surface in ("was", "were", "had"))
    tense = "future" if future else "past" if past else "present"
    obj = None
    if verb_at is not None:
        found = head_objects(tokens, verb_at + 1)
        obj = found[-1][0] if found else None
    is_conditional = any(w in CONDITIONALS for w in tokens)
    return subject, verb, aux, modal, negated, is_conditional, tense, passive, obj, complement


def clauses(sentence, mask):
    """[Clause] for `sentence`: split at every hard stop, comma, but and because; each clause's words give its fields."""
    shadow = _shadow(sentence, mask)
    stops = [m.start() for m in _BOUND.finditer(shadow) if m.group(1) or m.group(2)]
    softs = [m.start() for m in _STOP_ANY.finditer(shadow)]
    found, cur, lead, lead_at, lead_end = [], 0, "", 0, 0
    cuts = [(m.start(), m.end(), m.group(4) is not None, "" if m.group(4) else m.group().strip() or m.group())
            for m in _BOUND.finditer(shadow)]
    cuts.append((len(shadow), len(shadow), False, ""))
    for begin, stop, is_word, sep in cuts:
        if is_word and not shadow[cur:begin].strip():
            continue
        text = shadow[cur:begin]
        lo = cur + (len(text) - len(text.lstrip()))
        hi = cur + len(text.rstrip())
        if hi > lo:
            found.append((lo, hi, lead, lead_at, lead_end, sep))
            lead, lead_at, lead_end = sep, begin, stop
        elif sep and (not lead or sentence[cur:begin].strip()):  # a masked-only gap: the later separator leads
            lead, lead_at, lead_end = sep, begin, stop
        cur = begin if is_word else stop
    out = []
    for lo, hi, before, before_at, before_end, after in found:
        tokens = words(shadow[lo:hi])
        join = tokens[0] if tokens and tokens[0] in JOINERS + REASON_LINKS else None
        subject, verb, aux, modal, negated, cond, tense, passive, obj, complement = _analyse(tokens)
        reason_for = next((w for w in tokens if w in REASON_LINKS), None)
        hard = bisect.bisect_left(stops, lo)
        soft = bisect.bisect_left(softs, lo)
        out.append(Clause(lo, hi, join, subject, verb, aux, modal, negated, cond, tense, passive, obj, complement,
                          reason_for, before, after, stops[hard] if hard < len(stops) else len(shadow),
                          softs[soft] if soft < len(softs) else len(shadow), before_at, before_end))
    return out
