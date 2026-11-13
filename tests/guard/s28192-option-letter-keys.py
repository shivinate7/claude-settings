# section 28192
FAMILY = "option-letter-keys"
FAMILIES["option-letter-keys"] = "the page writer: an open decision's option keys are the lowercase letter of their position, unique, never none, its text names no option by a letter-and-digit key, and an option label that opens with a letter tag (B: x, Option B x) names the key's letter; a closed item is not judged; the page's letters are read from its own source"
#
# Rule option-letter-keys (decision option-keys-are-letters), built against a named incident: waiting item 77,
# Oct 30 15:09 CDT, and item 44 (key none), Oct 28 12:47 CDT. The page shows an option by its position, as a
# letter (skills/waiting-page/page.html, letterOf), so an option keyed a showed as B and the owner's "A" was
# misread. An option at index i takes the lowercase letter of the page's letter for i. The writer also refuses
# a key that is missing or not a string, a key that repeats, and the key none, which the page reads as "none of
# these". A task, a note and a closed item are not judged. An open item's text names no option by a
# letter-and-digit key, as in "option e2".

OL_DOC = "letter-keys"
OL_CTX = "The stamp check runs in the lint job today. The test job could run it too."
# The three options of the item's shape, with no key. ol_keyed gives them keys in position order.
OL_BASE = [
    {"label": "Keep the check in the lint job", "how": "Leave the workflow as it is.",
     "gain": "No change to review.", "lose": "The lint job stays the slow one."},
    {"label": "Move the check to the test job", "how": "Move the step to the test job.",
     "gain": "The lint job gets faster.", "lose": "The test job runs longer."},
    {"label": "Drop the check", "how": "Remove the step.", "gain": "Less runner time.", "lose": "No stamp check."},
]
ALPHA = [dict(OL_BASE[0], key=chr(97 + i), label="Path " + chr(97 + i)) for i in range(26)]


def ol_keyed(*keys):
    """The OL_BASE options, keyed `keys` in position order."""
    return [dict(OL_BASE[i], key=k) for i, k in enumerate(keys)]


def ol_opt(index, **over):
    """The a, b, c options of ol_item, with the option at `index` changed by `over`."""
    options = ol_keyed("a", "b", "c")
    options[index] = dict(options[index], **over)
    return options


def ol_item(**over):
    item = {"id": OL_DOC, "kind": "decision", "status": "open", "title": "Which CI job runs the stamp check?",
            "context": OL_CTX, "options": ol_keyed("a", "b", "c"), "pick": "a",
            "why": "The lint job already holds the other format checks."}
    item.update(over)
    return with_stake({k: v for k, v in item.items() if v is not None})


def ol(name, expected, item, action="set", **extra):
    wp_write("option letter keys: " + name, expected, "option-letter-keys", item, action=action,
             doc_id=OL_DOC, **extra)


def ol_write(data, op="set"):
    return {"op": op, "collection": "items", "doc_id": OL_DOC, "data": with_shown(data)}


# Keys by position: the page's letter for index i, lowercased.
ol("options keyed a, b and c are allowed", "allow", ol_item())
ol("keys a through z in position order are allowed", "allow", ol_item(options=ALPHA))
ol("options keyed e2, a and c are denied", "deny", ol_item(options=ol_keyed("e2", "a", "c")))
ol("options keyed a and c are denied", "deny", ol_item(options=ol_keyed("a", "c")))
ol("options keyed a and a are denied", "deny", ol_item(options=ol_keyed("a", "a")))
ol("item 44's shape, keyed a and none, is denied", "deny", ol_item(options=ol_keyed("a", "none")))
ol("options keyed none, b and c are denied", "deny", ol_item(options=ol_keyed("none", "b", "c")))
ol("options keyed A, b and c are denied, since the key is the lowercase letter", "deny",
   ol_item(options=ol_keyed("A", "b", "c")))
ol("keys b then a are denied", "deny", ol_item(options=ol_keyed("b", "a")))
ol("a keyless option at index 0 is denied", "deny", ol_item(options=[OL_BASE[0], dict(OL_BASE[1], key="b")]))
ol("a keyless option at index 1 is denied", "deny", ol_item(options=[dict(OL_BASE[0], key="a"), OL_BASE[1]]))
ol("an option whose key is null is denied", "deny", ol_item(options=ol_opt(0, key=None)))
ol("a multi item keyed a, b and c with a list pick is allowed", "allow", ol_item(multi=True, pick=["a", "c"]))
ol("a multi item keyed e2, a and c with a list pick is denied", "deny",
   ol_item(multi=True, options=ol_keyed("e2", "a", "c"), pick=["a", "c"]))

# Item text: an option named by a letter-and-digit key, after option, options, pick or key.
ol("a context that says option e2 is safer, keys a, b and c, is denied", "deny", ol_item(context="option e2 is safer"))
ol("a context that says Option e2 with a capital is denied", "deny",
   ol_item(context="Option e2 is safer for the stamp check."))
ol("a backticked key, option `e2`, is denied", "deny", ol_item(context="Keep option `e2` as it is."))
ol("a quoted key after pick is denied", "deny", ol_item(options=ol_opt(0, how='Pick "e2" to keep the check.')))
ol("a title that names option e2 is denied", "deny", ol_item(title="Option e2 or option b?"))
ol("a why that names key e2 is denied", "deny", ol_item(why="The key e2 keeps the lint job."))
ol("an option gain that names option e2 is denied", "deny", ol_item(options=ol_opt(0, gain="Option e2 keeps the check.")))
ol("a context that says the option to merge is allowed", "allow", ol_item(context="The option to merge is open."))
ol("a context that says option A is allowed", "allow", ol_item(context="Option A is the safer pick."))
ol("a context that says pick b is allowed", "allow", ol_item(context="Pick b for the lint job."))
ol("a context that says option 2 is allowed", "allow", ol_item(context="Option 2 is the safer pick."))

# The forms a session writes between the word and the key: a colon, a bracket, markdown emphasis.
ol("a context that says Option: e2 is denied", "deny", ol_item(context="Option: e2 is the safer pick."))
ol("a context that says Option (e2) is denied", "deny", ol_item(context="Option (e2) is the safer pick."))
ol("a context that says Pick **e2** is denied", "deny", ol_item(context="Pick **e2** to keep the check."))
ol("a context that says Option [e2] is denied", "deny", ol_item(context="Option [e2] is the safer pick."))
ol("a why that says key: e2 is denied", "deny", ol_item(why="The key: e2 keeps the lint job."))

# The page shows an option's letter in capitals, so Claude can write "Option E2" for key e2. That is the incident
# form (waiting item 77), so a key takes either case after the word.
ol("a context that says Option E2 with a capital key is denied", "deny",
   ol_item(context="Option E2 is safer for the stamp check."))
ol("a context that says Pick **E2** with a capital key is denied", "deny",
   ol_item(context="Pick **E2** to keep the check."))

# Ids this repo cites are not keys. D12 is a decision id and t18 is the owner's topic id for the uniform ruling.
# A lowercase d-and-digit word after "key" has a key's shape, so it is refused like "key e2": the exempt ids are
# D<digits> and t<digits>, not every letter that an id could start with. A1 is not exempt: folding case on the key
# refuses A1 too, and that cost is accepted, so "Pick A1" is refused.
ol("a context that says Option D12 is allowed", "allow", ol_item(context="Option D12 is the short-titles ruling."))
ol("a context that says Option t18 is allowed", "allow", ol_item(context="Option t18 is the uniform ruling."))
ol("a context that says Pick A1 is denied, since a key folds case", "deny", ol_item(context="Pick A1 on the sheet."))
ol("a context that says key d4 is denied, since it has a key's shape", "deny", ol_item(context="The key d4 stays."))

# A closed item records what was decided, so its old keys and its text are not judged, as in decision_form_hit.
ol("a whole-item set of a closed item keyed e2, a and c is allowed", "allow",
   ol_item(status="closed", options=ol_keyed("e2", "a", "c")))
ol("a whole-item set of a closed item whose context says option e2 won is allowed", "allow",
   ol_item(status="closed", context="Option e2 won."))

# A str_replace carries no status, so it is judged on the text it adds: new_str, never old_str.
ol("a str_replace that adds Option e2 wins. to context is denied", "deny", None, action="str_replace",
   field="context", old_str="The test job could run it too.", new_str="Option e2 wins.")
ol("a str_replace that adds Option b wins. to context is allowed", "allow", None, action="str_replace",
   field="context", old_str="The test job could run it too.", new_str="Option b wins.")
ol("a str_replace that takes option e2 out of context is allowed", "allow", None, action="str_replace",
   field="context", old_str="Option e2 wins.", new_str="Option a wins.")

# Kind: an item with no kind is a decision. A task and a note are not judged.
ol("an item with no kind is judged as a decision and denied", "deny",
   ol_item(kind=None, options=ol_keyed("e2", "a", "c")))
ol("a task keyed e2, a and c is not judged", "allow",
   ol_item(kind="task", options=ol_keyed("e2", "a", "c"), context=OL_CTX + "\n" + TN_WHY))
ol("a note keyed e2, a and c is not judged", "allow", ol_item(kind="note", options=ol_keyed("e2", "a", "c")))

# Updates: judged when they carry options; the kind defaults to decision.
ol("an update that carries options keyed x and y is denied", "deny", {"options": ol_keyed("x", "y")},
   action="update")
ol("an update that carries options keyed a, b and c is allowed", "allow", {"options": ol_keyed("a", "b", "c")},
   action="update")
ol("an update that carries options keyed a and none is denied", "deny", {"options": ol_keyed("a", "none")},
   action="update")
ol("a set to another artifact is allowed", "allow", ol_item(options=ol_keyed("e2", "a", "c")),
   url="https://claude.ai/artifact/other")
add("option letter keys: a batch with one item keyed e2, a and c is denied", "deny", "option-letter-keys",
    tool="ArtifactData", cwd=PQ_REPO, url=PQ_URL, action="batch",
    writes=[ol_write(ol_item()), ol_write(ol_item(options=ol_keyed("e2", "a", "c")))])
add("option letter keys: a batch of keyed items is allowed", "allow", tool="ArtifactData", cwd=PQ_REPO,
    url=PQ_URL, action="batch", writes=[ol_write(ol_item()), ol_write(ol_item(multi=True, pick=["a", "c"]))])

# An option's label that opens with a letter tag must name the key's letter. Incident, Nov 1 16:12 CST: options
# keyed a, b, c, d carried the labels B, D, A and C, so the owner's answer letter was ambiguous. A letter with no
# tag shape, such as "A rail", is ordinary text and is not judged.
def ol_labelled(*labels):
    """Options keyed in position order, each with its label: ol_labelled("B: x") keys one option a."""
    return [dict(OL_BASE[0], key=chr(97 + i), label=label) for i, label in enumerate(labels)]


INCIDENT_LABELS = ("B: a bottom strip", "D: drag sideways", "A: a rail", "C: a grab line")
ol("the Nov 1 incident item, keyed a, b, c, d under labels B, D, A and C, is denied", "deny",
   ol_item(options=ol_labelled(*INCIDENT_LABELS)))

# One tag form each, on the option at position 0 keyed a. Each tag names a letter other than a.
TAG_FORMS = ("B: x", "B) x", "B. x", "(B) x", "[B] x", "B — x", "B - x", "Option B x", "option b: x",
             "**B:** x")
for tag_form in TAG_FORMS:
    ol("label %r keyed a at position 0 is denied" % tag_form, "deny", ol_item(options=ol_opt(0, label=tag_form)))

# Text that looks like a tag but is not one: no delimiter after the letter, or a letter inside a word or an id.
# A letter is judged only when the label opens with its tag, so each of these is ordinary text at its position.
ol("label 'A rail' keyed b at position 1 is allowed, since no tag opens it", "allow",
   ol_item(options=ol_opt(1, label="A rail")))
ol("label 'I think x' keyed c at position 2 is allowed", "allow", ol_item(options=ol_opt(2, label="I think x")))
ol("label 'A/B test' keyed c at position 2 is allowed", "allow", ol_item(options=ol_opt(2, label="A/B test")))
ol("label 'AI-first' keyed b at position 1 is allowed", "allow", ol_item(options=ol_opt(1, label="AI-first")))
ol("label 'X-ray' keyed c at position 2 is allowed", "allow", ol_item(options=ol_opt(2, label="X-ray")))
ol("label 'B2B' keyed a at position 0 is allowed", "allow", ol_item(options=ol_opt(0, label="B2B")))
ol("label 'E.g. x' keyed b at position 1 is allowed", "allow", ol_item(options=ol_opt(1, label="E.g. x")))
ol("label 'A-frame' keyed b at position 1 is allowed", "allow", ol_item(options=ol_opt(1, label="A-frame")))
ol("label 'A: a rail' keyed a at position 0 is allowed, since its tag matches the key", "allow",
   ol_item(options=ol_opt(0, label="A: a rail")))
ol("the incident labels on a closed item are allowed, since a closed item is not judged", "allow",
   ol_item(status="closed", options=ol_labelled(*INCIDENT_LABELS)))


# The page's letters and none. The guard's copy must match them: the page's letterOf maps index i to
# String.fromCharCode(65 + i % 26), and NONE is "none". Each check reads one line, anchored at a line start,
# so a copy in a comment never stands for the page's line.
PAGE_HTML = os.path.join(REPO, "skills", "waiting-page", "page.html")
PAGE_LETTER_CALL = re.compile(r"const i = \(it\.options \|\| \[\]\)\.findIndex\(\(o\) => o\.key === key\);")
PAGE_LETTER_MAP = re.compile(r"String\.fromCharCode\(65 \+ i % 26\)")


def page_letter_problem(text):
    """'' when the page's letterOf maps index i to String.fromCharCode(65 + i % 26), else what differs."""
    defs = [line for line in text.splitlines() if re.match(r"\s*const letterOf\s*=", line)]
    if len(defs) != 1:
        return "want one const letterOf line, found %d" % len(defs)
    if not PAGE_LETTER_CALL.search(defs[0]):
        return "letterOf does not read the index of the option it is given"
    if not PAGE_LETTER_MAP.search(defs[0]):
        return "letterOf does not map index i to String.fromCharCode(65 + i % 26)"
    return ""


def page_none_problem(text):
    """'' when the page sets NONE to "none", else what differs."""
    defs = [line for line in text.splitlines() if re.match(r"\s*const NONE\s*=", line)]
    if len(defs) != 1 or not re.match(r'\s*const NONE = "none";\s*$', defs[0]):
        return 'want one line const NONE = "none";'
    return ""


def page_letters_check():
    with open(PAGE_HTML, encoding="utf-8") as handle:
        text = handle.read()
    problem = page_letter_problem(text) or page_none_problem(text)
    return (not problem), (problem or "the page's letterOf and NONE are the letters the guard checks")


LOG_CHECKS_EXTRA.append(("option letter keys: the page's letterOf and NONE are the letters the guard checks",
                         page_letters_check))

# Scanner cases for page_letter_problem: a comment copy, a lone quote in a comment, and a template literal copy.
LETTER_RIGHT = ('const letterOf = (it, key) => { const i = (it.options || []).findIndex((o) => o.key === key); '
                'return i < 0 ? "" : String.fromCharCode(65 + i % 26); };')
LETTER_WRONG = LETTER_RIGHT.replace("65 + i", "66 + i")


def page_text_check(text, want_problem):
    """A checker that runs page_letter_problem on synthetic page text and wants a problem, or none."""
    def check():
        problem = page_letter_problem(text)
        if bool(problem) != want_problem:
            return False, "want %s, got %r" % ("a problem" if want_problem else "no problem", problem)
        return True, "as wanted"
    return check


LOG_CHECKS_EXTRA.append(("option letter keys: a comment copy of letterOf does not stand for the page's line",
                         page_text_check("// " + LETTER_RIGHT + "\n" + LETTER_WRONG, True)))
LOG_CHECKS_EXTRA.append(("option letter keys: a lone quote in a comment does not hide letterOf",
                         page_text_check("// The owner's page keeps this line.\n" + LETTER_RIGHT, False)))
LOG_CHECKS_EXTRA.append(("option letter keys: a template literal copy of letterOf fails the check as ambiguous",
                         page_text_check("const doc = `\n" + LETTER_WRONG + "\n`;\n" + LETTER_RIGHT, True)))


# --------------------------------------------------------------------------- a reworked item is not answered on the page
