"""Pass-claim check (rule pass-claim-cites-verdict): one detector and one cite reader, imported by two hooks.

Incident: a session read its own `echo $?` as "lane lint passes". A sentence that says a check passed, is green or
is clean, with a check noun near the claim word, must be backed by a verdict line in the sending session's own
transcript. `lint/report_guard.py` (the Stop hook) judges the report blockquote with `problem`. `hooks/guard.py` (the
PreToolUse hook) judges a SendMessage and a claude-code-remote send_message with `send_problem`.

The cite is the verbatim `PASS <cmd> (<secs>s)` line in the result of a non-sidechain Bash call whose program is
verdict (bin/verdict prints it; <cmd> is the words verdict ran, `~` and `$HOME` expanded on both sides). The cite must
match the claim's check: a lint, ci-job or checks claim needs a roster command (the one `check_stage` reads in
guard_stream), a tests, suite or checks claim needs a command that names a test, and `verdict true` backs nothing. The
newest verdict line per command wins, so a FAIL after a PASS of the same command cancels it. A SKIP line backs no
claim. Text in a reply, an Agent result, a sidechain call or a bare run is no cite.

Cost: reads the transcript only when a claim is found. No file written, no process started. Fails open on any error,
with one stderr line.
"""
import json
import os
import re
import sys

CLAIM_WORDS = frozenset(("passed", "passes", "pass", "green", "clean"))
# Words that stand before the noun: "green lint", "clean checks". The others follow their noun only, so
# "passed the brief to the lint lane" is no claim.
ADJECTIVES = frozenset(("green", "clean"))
# Each check noun and the kinds of verdict command that back it. A roster command is one `check_stage` names
# (merge --lane-lint, merge --review-record, merge --release-check, ci-job); a test command names a test. CI and build
# are no noun: no verdict run can cite a GitHub CI result.
NOUN_NEEDS = {"lint": frozenset(("roster",)), "cijob": frozenset(("roster",)), "tests": frozenset(("test",)),
              "suite": frozenset(("test",)), "checks": frozenset(("roster", "test"))}
HYPHEN_WORDS = (("ci-job", "cijob"), ("test-author", "testauthor"), ("record-writer", "recordwriter"))
NOUN_GAP = 4      # words between the claim word and its check noun
CUE_GAP = 4       # words before the claim word, in its own clause, that hold a negation or a condition
ATTRIBUTION_GAP = 5  # words before the claim word, in any clause, that hold the one who says it
NEGATIONS = frozenset(("not", "never", "no", "nothing", "cannot"))
CONDITIONS = frozenset((
    "if", "when", "once", "until", "unless", "whether", "will", "would", "should", "must", "to", "can", "could", "may",
    "might", "make", "get", "gets", "getting", "need", "needs", "want", "wants", "expect", "expected"))
ATTRIBUTIONS = frozenset((
    "reviewer", "reviewers", "builder", "builders", "testauthor", "recordwriter", "refuter", "designer", "agent",
    "agents", "subagent", "reports", "reported", "says", "said", "claims", "claimed", "according"))
BOUNDARY = "|"  # a comma, semicolon, parenthesis or dash ends a clause

FENCE_RE = re.compile(r"```.*?```", re.S)
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?|[,;()—–]|\s[-–—]{1,2}\s")
# A count: "12 passed", "3/5 passed", "3/5 tests passed". A number ahead of a plain noun ("PR 7 lint passed") is no count.
COUNT_NOUNS = "(?:tests?|checks?|suites?|cases|jobs|files|specs)"
STAT_RE = re.compile(r"\b\d+(?:/\d+)?\s+(?:%s\s+)?(?:passed|passes|pass|green|clean)\b" % COUNT_NOUNS, re.I)
REDIRECT_RE = re.compile(r"^(?:\d*[<>]|&>)")
PASS_RE = re.compile(r"^PASS (.+) \(\d+(?:\.\d+)?s\)\s*$")
FAIL_RE = re.compile(r"^FAIL (.+?) rc=\d+")
SKIP_RE = re.compile(r"^SKIP (.+?), \d+ skipped \(")
LINE_FORMS = (("PASS", PASS_RE), ("FAIL", FAIL_RE), ("SKIP", SKIP_RE))
TEST_COMMAND_RE = re.compile(
    r"(?:^|[\s/\\])(?:test[_.-]\S*|\S*[_.-]tests?\.\w+)|\b(?:pytest|unittest|jest|vitest)\b"
    r"|\b(?:npm|yarn|pnpm|cargo|go|swift|xcodebuild|make|uv)\s+(?:run\s+)?test\b|\s--test\b|(?:^|\s)tests?/", re.I)


def _negates(token):
    return token in NEGATIONS or token.endswith(("n't", "n’t"))


def _words(text):
    """The text's tokens, lower case: words, and BOUNDARY for each clause break."""
    text = text.lower()
    for hyphen, joined in HYPHEN_WORDS:
        text = text.replace(hyphen, joined)
    return [t if t[0].isalnum() else BOUNDARY for t in TOKEN_RE.findall(text)]


def _span(found):
    """A backtick span: kept bare when it is one word, so "Lint `passed`." still reads, else dropped as a quote."""
    inner = found.group()[1:-1]
    return " " + inner + " " if re.fullmatch(r"[A-Za-z-]+", inner) else " "


def _sentence_needs(sentence):
    """The need of each check noun a sentence claims passed: [] when it claims none. A claim is a claim word with a
    check noun beside it, and none of the exempt forms: a negation or condition in its clause, a named speaker in the
    five words before it, a count."""
    tokens = _words(STAT_RE.sub(" ", sentence))
    needs = []
    for at, word in enumerate(tokens):
        if word not in CLAIM_WORDS:
            continue
        before = [t for t in tokens[:at] if t != BOUNDARY][-NOUN_GAP:]
        after = [t for t in tokens[at + 1:] if t != BOUNDARY][:NOUN_GAP] if word in ADJECTIVES else []
        nouns = [t for t in before + after if t in NOUN_NEEDS]
        if not nouns:
            continue
        clause = []
        for token in reversed(tokens[:at]):
            if token == BOUNDARY or len(clause) == CUE_GAP:
                break
            clause.append(token)
        if any(_negates(t) or t in CONDITIONS for t in clause):
            continue
        if any(t in ATTRIBUTIONS for t in [t for t in tokens[:at] if t != BOUNDARY][-ATTRIBUTION_GAP:]):
            continue
        needs += [NOUN_NEEDS[n] for n in dict.fromkeys(nouns)]
    return needs


def claims_in(text):
    """[(sentence, needs)] for each sentence of `text` that says a check passed. Text in a fence, a claim in
    backticks, and a question, are no claim."""
    text = CODE_SPAN_RE.sub(_span, FENCE_RE.sub(" ", text))
    found = []
    for sentence in SENTENCE_RE.split(text):
        sentence = sentence.strip()
        needs = [] if not sentence or sentence.endswith("?") else _sentence_needs(sentence)
        if needs:
            found.append((sentence, needs))
    return found


def _normal(command):
    """A command text as the shell passes it on: `~` and `$HOME` expanded in each word."""
    return " ".join(os.path.expanduser(os.path.expandvars(word)) for word in command.split())


def verdict_commands(command):
    """The command texts that `verdict` runs in one shell command: the words after the verdict word, as bin/verdict
    joins them into the name of its PASS line. The shell parser is guard_core's, the verdict words and the `uv run`
    read guard_stream's."""
    from guard_core import basename, resolve_command, segment_tokens, split_segments, strip_heredoc_bodies
    from guard_stream import VERDICT_WORDS, _skip_uv_run
    ran = []
    for segment in split_segments(strip_heredoc_bodies(command)):
        tokens = segment_tokens(segment)
        at = resolve_command(tokens) if tokens else None
        if at is None:
            continue
        at = _skip_uv_run(tokens, at)
        word = next((i for i in range(at) if basename(tokens[i].lstrip("(")) in VERDICT_WORDS), None)
        if word is None:
            continue
        argv = []
        for token in tokens[word + 1:]:
            if REDIRECT_RE.match(token):
                break
            argv.append(token)
        if argv:
            ran.append(_normal(" ".join(argv)))
    return ran


def _kinds(command):
    """The kinds of check a verdict command backs: "roster" for a named check (guard_stream's one roster), "test" for
    a command that names a test. `verdict true` backs none."""
    from guard_stream import check_stage, test_run_stage
    kinds = set()
    if check_stage(command, False, True) and not test_run_stage(command):
        kinds.add("roster")
    if TEST_COMMAND_RE.search(command):
        kinds.add("test")
    return kinds


def _result_text(content):
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


def backed_kinds(records):
    """The kinds of check the transcript cites: for each command, its newest verdict line in a non-sidechain Bash
    call's result, and the kinds of the commands whose newest line is a PASS."""
    status = {}
    ran_by_call = {}
    for rec in records:
        content = (rec.get("message") or {}).get("content") if isinstance(rec.get("message"), dict) else None
        if rec.get("isSidechain") or not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                shown = block.get("input")
                command = shown.get("command") if isinstance(shown, dict) else None
                ran = verdict_commands(command) if isinstance(command, str) and "verdict" in command else []
                if ran:
                    ran_by_call[block.get("id")] = ran
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in ran_by_call:
                ran = ran_by_call[block.get("tool_use_id")]
                for line in _result_text(block.get("content")).splitlines():
                    for kind, form in LINE_FORMS:
                        found = form.match(line)
                        name = _normal(found.group(1)) if found else ""
                        if name in ran:
                            status[name] = kind
    backed = set()
    for name, kind in status.items():
        if kind == "PASS":
            backed |= _kinds(name)
    return backed


def _read(path):
    """The transcript's records, one JSON object a line; a line that is not one is skipped."""
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                records.append(rec)
    return records


def _unbacked(found, records):
    """The first claiming sentence of `found` (cut to 120 characters) whose check the transcript does not cite, else ''.
    The transcript is read only when a claim is found."""
    if not found:
        return ""
    backed = backed_kinds(records)
    return next((s[:120] for s, needs in found if any(not need & backed for need in needs)), "")


def problem(text, records):
    """The claiming sentence when `text` claims a pass that `records` do not cite, else ''."""
    return _unbacked(claims_in(text), records)


def send_problem(message, transcript_path):
    """`problem` for an outgoing message, reading the transcript at `transcript_path` only when the message claims.
    Fails open: an error, or no transcript to read, lets the message through with one stderr line."""
    try:
        found = claims_in(message) if isinstance(message, str) else []
        if not found:
            return ""
        if not isinstance(transcript_path, str) or not transcript_path:
            print("pass-claim guard failed open: no transcript to read", file=sys.stderr)
            return ""
        return _unbacked(found, _read(transcript_path))
    except Exception as exc:
        print("pass-claim guard failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return ""
