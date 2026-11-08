"""The clause parser the cannot-claim check reads: sentences, clauses and the lexicons of their grammar.

`lint/report_guard.py` imports this module, so the check has one copy of its sentence and clause boundaries and one home
for each word list (NEGATORS, ADVERBS, CONDITIONALS, REASON_LINKS, DETERMINERS, CANNOT_FORMS). The module reads text and
a mask only: no file, no process. Its cost is one regex pass over a sentence and one over each clause, so the work grows
in step with the text.

sentences(text, mask) -> [(start, end)]: the spans tile the text and each keeps its terminator. `mask` holds one bool per
character, True inside a code span or a quote: the parser reads those characters as blanks and reads no quote itself.
clauses(sentence, mask) -> [Clause]: a clause ends at ; : ! ? a dash, a comma, or a but or because, and the word that
opens it (and, but, or, so, yet, then, because) is its `join`. `lead` and `term` are the separators before and after it;
`hard_end` is where the nearest hard stop (. ; : ! ? a dash) at or after the clause sits, and `sent_end` the nearest of
. ; : ! ?; both are offsets into the sentence. A clause's other fields are read from its words alone.
"""
import re
from typing import NamedTuple, Optional

NEGATORS = ("not", "n't", "never", "no")
ADVERBS = ("even", "yet", "currently", "actually", "really", "still", "also", "just", "now", "directly", "simply",
           "unfortunately")
CONDITIONALS = ("if", "unless", "whether", "would")
REASON_LINKS = ("because",)
DETERMINERS = ("a", "an", "the", "this", "that", "these", "those", "its", "their", "his", "her", "our", "my", "your")
JOINERS = ("and", "but", "or", "so", "yet", "then")
PREPOSITIONS = ("for", "of", "in", "on", "to", "from", "with", "about", "against", "at", "by", "per")
# The phrases that say a session cannot do an act. A form reads the same with n't or not and with a curly apostrophe.
CANNOT_FORMS = ("can't", "cannot", "can not", "unable to", "could not", "couldn't", "no way to", "no way I can",
                "no way we can", "not able to", "wasn't able to", "won't be able to", "will not be able to",
                "haven't been able to", "hasn't been able to", "have not been able to", "has not been able to",
                "not allowed to", "not permitted to", "not going to be able to")
WINDOW = 6  # words after a phrase, in its clause, that may name the act
NEGATOR_GAP = 3  # words before a phrase that a negator may sit in and still negate it

_STOPS = PREPOSITIONS + ("without", "into", "onto", "over", "under", "through", "via", "than", "as", "like")
_PRONOUNS = ("i", "we", "you", "he", "she", "it", "they", "there", "here")
_CONTRACTED = {"i'm": ("i", "am"), "we're": ("we", "are"), "you're": ("you", "are"), "they're": ("they", "are"),
               "it's": ("it", "is"), "he's": ("he", "is"), "she's": ("she", "is"), "there's": ("there", "is"),
               "i've": ("i", "have"), "we've": ("we", "have"), "i'll": ("i", "will"), "we'll": ("we", "will"),
               "i'd": ("i", "would"), "we'd": ("we", "would")}
_MODALS = ("can", "could", "would", "will", "shall", "should", "may", "might", "must")
_BE = ("is", "are", "was", "were", "be", "been", "being", "am")
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
_BOUND = re.compile(r"(\s-{1,2}\s)|([;:!?—–]|\.(?!\w))|(,)|\b(but|because)\b", re.I)
_STOP_ANY = re.compile(r"[.;:!?]")
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


def conditional(text):
    """True when `text` holds a word of CONDITIONALS."""
    return any(w in CONDITIONALS for w in words(text))


def negated_near(text, gap=NEGATOR_GAP):
    """True when a negator (NEGATORS) sits in the last `gap` words of `text`."""
    return any(w in NEGATORS or w.endswith("n't") for w in words(" ".join(text.split()[-gap:])))


def first_words(text, count=WINDOW):
    """The first `count` words of `text`, as written, joined by one space."""
    return " ".join(text.split()[:count])


def own_subject(before, own):
    """True when the words just before a phrase end in a subject of `own` (a set of lowercase word tuples), or hold no
    subject at all: the phrase opens its clause. A trailing adverb (ADVERBS) is skipped, and so is the auxiliary
    (am, are, was, were, have, has, had) after I or we."""
    tokens = words(before)
    while tokens and tokens[-1] in ADVERBS:
        tokens.pop()
    if not tokens:
        return True
    for k in (3, 2, 1):
        if tuple(tokens[-k:]) in own:
            return True
    if len(tokens) > 1 and tokens[-1] in ("am", "are", "was", "were", "have", "has", "had") and tokens[-2] in ("i", "we"):
        return True
    return False


def past_phrase(phrase, before):
    """True when a phrase reports a failure: could not, wasn't able, or any phrase right after was or were."""
    lowered = phrase.lower().replace("’", "'")
    tokens = words(before)
    while tokens and tokens[-1] in ADVERBS:
        tokens.pop()
    return lowered.startswith(("could", "wasn't")) or bool(tokens) and tokens[-1] in ("was", "were") and bool(before.split())


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
    found, cur, lead = [], 0, ""
    cuts = [(m.start(), m.end(), m.group(4) is not None, "" if m.group(4) else m.group().strip() or m.group())
            for m in _BOUND.finditer(shadow)]
    cuts.append((len(shadow), len(shadow), False, ""))
    for begin, stop, is_word, sep in cuts:
        if is_word:
            if not shadow[cur:begin].strip():
                continue
            sep = ""
            nxt = begin
        else:
            nxt = stop
        text = shadow[cur:begin]
        lo = cur + (len(text) - len(text.lstrip()))
        hi = cur + len(text.rstrip())
        if hi > lo:
            found.append([lo, hi, lead, sep, shadow[lo:hi]])
            lead = sep
        elif sep:
            lead = sep
        cur = nxt
    out, hard, soft = [], 0, 0
    for lo, hi, before, after, text in found:
        while hard < len(stops) and stops[hard] < hi:
            hard += 1
        while soft < len(softs) and softs[soft] < hi:
            soft += 1
        tokens = words(text)
        join = tokens[0] if tokens and tokens[0] in JOINERS + REASON_LINKS else None
        subject, verb, aux, modal, negated, cond, tense, passive, obj, complement = _analyse(tokens)
        reason_for = next((w for w in tokens if w in REASON_LINKS), None)
        out.append(Clause(lo, hi, join, subject, verb, aux, modal, negated, cond, tense, passive, obj, complement,
                          reason_for, before, after, stops[hard] if hard < len(stops) else len(shadow),
                          softs[soft] if soft < len(softs) else len(shadow)))
    return out
