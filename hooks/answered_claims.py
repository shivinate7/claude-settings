#!/usr/bin/env python3
"""The answered-claim judge: a sent message or a brief that says a waiting-page item is answered, when the page's
data in git holds no owner answer for that item, is refused.

Rule: brief-checks-answered-claims-match-page (decision answered-claims-match-page). guard.py calls
answered_claim_hit(tool, tool_input, cwd) before a send_message, a SendMessage or a create_session. It returns
(matched, reason) for a refusal and None for everything else. Standard library only.

Judged text: `message` of the claude-code-remote send_message and of SendMessage, `prompt` of create_session.

A claim is one sentence that holds an item reference (`item <n>`, `item #<n>`, `page:<n>`), the whole word
answered, approved or ruled, and no negator before that word in its clause (lint/report_guard.py
ANSWERED_NEGATOR_RE). A sentence that ends in `?` claims nothing. Fenced blocks and inline code spans are skipped.
A claim by an item id slug alone is not judged.

The page's data is read from git, never from the live page. The folder and the record branch come from
feedback_guard.waiting_copy. The refs read are the local record branch and origin's, both when both exist. An
item counts as answered when answers/<id>.json holds its number in either ref, or its items/<id>.json holds the
number and a lastAnswer key. A number found with no answer refuses. A number not in the store, a missing ref or
registry, a layout or git error and a timeout allow, with one stderr line: unknown is not clear.

Cost: no process unless a claim sentence exists. Then at most two git starts (for-each-ref, then one grep) under
one 5 s deadline. No file is written here.
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _nowindow  # noqa: E402  the one home of a no-window child start
from shared_names import REMOTE_SERVER  # noqa: E402  the one home of the remote tool prefix

RULE = "brief-checks-answered-claims-match-page"
TEXT_FIELDS = {"SendMessage": "message", REMOTE_SERVER + "__send_message": "message",
               REMOTE_SERVER + "__create_session": "prompt"}
GIT_DEADLINE = 5  # seconds for the whole page read: the ref list, then the one grep
CLAIM_WORD = re.compile(r"(?<![\w-])(?:answered|approved|ruled)(?![\w-])", re.I)
ITEM_REF = re.compile(r"(?<!\w)item\s+#?(\d+)(?!\w)|(?<!\w)page:#?(\d+)(?!\w)", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")
QUESTION_END = re.compile(r"\?[*_)\"'\s]*$")
GREP_LINE = re.compile(r"^[^:]+:[^:]*/(items|answers)/[^:/]+\.json:\s{2}\"(n|lastAnswer)\":\s*(\d*)")
GREP_PATH = re.compile(r"^([^:]+:[^:]*/(?:items|answers)/[^:/]+\.json):")
REASON = ("The page data in git shows no owner answer for item %s, so this sentence claims an answer the owner has not "
          "given: \"%s\". Cite the owner's answer and its time, or say \"recommended, not answered\". If the owner "
          "answered after the last export, the page writer exports first (skill waiting-page). An owner override "
          "lifts this refusal. (decision answered-claims-match-page, a claim of an answer matches the page)")


def judged_text(tool, tool_input):
    """The text of the call that this check reads, or ""."""
    field = TEXT_FIELDS.get(tool)
    text = tool_input.get(field) if field and isinstance(tool_input, dict) else None
    return text if isinstance(text, str) else ""


def claims(text):
    """[(sentence, [item numbers])] for each claim sentence of `text`, in order. Prefilters on the two cheap tests
    first, so a message with no claim imports nothing and starts nothing."""
    if not CLAIM_WORD.search(text) or not ITEM_REF.search(text):
        return []
    lint = os.path.join(HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)  # the guard runs with hooks/ alone on the path
    import report_guard  # lint/report_guard.py: the negator, the clause break, the code span and the line reader
    found = []
    for body in report_guard._prose_lines(text, questions=True):
        plain = report_guard.CODE_SPAN.sub(" ", body)
        for sentence in SENTENCE_END.split(plain):
            sentence = sentence.strip()
            if not sentence or QUESTION_END.search(sentence):
                continue
            numbers = [a or b for a, b in ITEM_REF.findall(sentence)]
            if numbers and any(_claims_word(report_guard, sentence)):
                found.append((sentence, numbers))
    return found


def _claims_word(report_guard, sentence):
    """One bool per claim word: True when no negator sits in the word's clause before it."""
    for match in CLAIM_WORD.finditer(sentence):
        clause = report_guard.ANSWERED_CLAUSE_BREAK_RE.split(sentence[:match.start()])[-1]
        yield not report_guard.ANSWERED_NEGATOR_RE.search(clause)


def read_page(root):
    """(set of item numbers in the store, set of answered numbers, why not). `why not` is "" when the store was
    read, else the reason it was not. Two git starts at most, one deadline."""
    import feedback_guard
    import question_form
    layout = question_form._layout()
    try:
        branch, folder = feedback_guard.waiting_copy(layout, root)
    except layout.LayoutError as error:
        return set(), set(), "the layout is unreadable (%s)" % " ".join(str(error).split())[:100]
    deadline = time.monotonic() + GIT_DEADLINE
    env = dict(os.environ, LC_ALL="C")

    def git(*args):
        done = _nowindow.run(["git", "-C", root, *args], stdin=subprocess.DEVNULL, capture_output=True, env=env,
                             timeout=max(0.1, deadline - time.monotonic()))
        return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")

    wanted = ["refs/heads/" + branch, "refs/remotes/origin/" + branch]
    code, out, err = git("for-each-ref", "--format=%(refname)", *wanted)
    if code:
        return set(), set(), "git for-each-ref exit %d: %s" % (code, " ".join(err.split())[:100])
    refs = [ref for ref in wanted if ref in set(out.split())]
    if not refs:
        return set(), set(), "the record branch %s is in neither the local refs nor origin" % branch
    code, out, err = git("grep", "-I", "--no-color", "-E", "-e", r'^  "(n|lastAnswer)":', *refs, "--",
                         folder + "/items", folder + "/answers")
    if code not in (0, 1) or err.strip():  # exit 1 with no stderr is "no lines"
        return set(), set(), "git grep exit %d: %s" % (code, " ".join(err.split())[:100])
    numbers, answered, has_answer, number_of = set(), set(), set(), {}
    for line in out.splitlines():
        match, path = GREP_LINE.match(line), GREP_PATH.match(line)
        if not match or not path:
            return set(), set(), "git grep printed an odd line"
        kind, key, value = match.groups()
        if key == "lastAnswer":
            has_answer.add(path.group(1))
        elif value:
            numbers.add(value)
            number_of[path.group(1)] = (kind, value)
            if kind == "answers":
                answered.add(value)
    for path in has_answer:
        if path in number_of and number_of[path][0] == "items":
            answered.add(number_of[path][1])
    return numbers, answered, ""


def answered_claim_hit(tool, tool_input, cwd):
    """(matched, reason) when the call claims an answer the page's data in git does not hold, else None. Never
    raises: a page that cannot be read allows, with one stderr line."""
    text = judged_text(tool, tool_input)
    if not text:
        return None
    try:
        found = claims(text)
        if not found:
            return None
        import question_form
        root = question_form._git_root_of(cwd) if isinstance(cwd, str) and cwd else None
        if root is None:
            why = "the call has no repo to read the page from"
        else:
            numbers, answered, why = read_page(root)
    except Exception as error:
        found, why = [], "%s: %s" % (type(error).__name__, " ".join(str(error).split())[:100])
    if not why:
        unknown = False
        for sentence, refs in found:
            for number in (str(int(n)) for n in refs):
                if number in answered:
                    continue
                if number in numbers:
                    shown = sentence.rstrip(".!;")
                    return shown, REASON % (number, shown)
                unknown = True
        why = "the claimed item is not in the page's data" if unknown else ""
    if why:
        print("answered-claim check failed open: %s" % why, file=sys.stderr)
    return None
