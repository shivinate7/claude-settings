"""Pass-claim check (rule pass-claim-cites-verdict): one detector and one cite reader, imported by two hooks.

Incident: a session read its own `echo $?` as "lane lint passes". A sentence that says a check passed, is green or
is clean, with a check noun near the claim word, must be backed by a verdict line in the sending session's own
transcript. `lint/report_guard.py` (the Stop hook) judges the report blockquote with `problem`. `hooks/guard.py` (the
PreToolUse hook) judges a SendMessage and a claude-code-remote send_message with `send_problem`.

The cite is the verbatim `PASS <cmd> (<secs>s)` line in the result of a non-sidechain Bash call whose program is
verdict (bin/verdict prints it; <cmd> is the words verdict ran). The newest verdict line per command wins, so a FAIL
after a PASS of the same command cancels it. A SKIP line backs no claim. Text in a reply, an Agent result, a sidechain
call or a bare run is no cite.

Cost: reads the transcript only when a claim is found. No file written, no process started. Fails open on any error,
with one stderr line.
"""
import json
import re
import sys

CLAIM_WORDS = frozenset(("passed", "passes", "green", "clean"))
# Words that stand before the noun: "green CI", "clean build". "passed" and "passes" follow their noun only, so
# "passed the brief to the build lane" is no claim.
ADJECTIVES = frozenset(("green", "clean"))
CHECK_NOUNS = frozenset(("lint", "ci", "tests", "checks", "suite", "cijob", "build"))
HYPHEN_WORDS = (("ci-job", "cijob"), ("test-author", "testauthor"), ("record-writer", "recordwriter"))
NOUN_GAP = 4      # tokens between the claim word and its check noun
CUE_GAP = 4       # tokens before the claim word that hold a negation or a condition
ATTRIBUTION_GAP = 5  # tokens before the claim word that hold the one who says it
NEGATIONS = frozenset(("not", "never", "no", "nothing", "cannot"))
CONDITIONS = frozenset(("if", "when", "once", "until", "unless", "whether", "will", "would", "should", "must"))
ATTRIBUTIONS = frozenset((
    "reviewer", "reviewers", "builder", "builders", "testauthor", "recordwriter", "refuter", "designer", "agent",
    "agents", "subagent", "reports", "reported", "says", "said", "claims", "claimed", "according"))

FENCE_RE = re.compile(r"```.*?```", re.S)
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
# A statistic: "12 passed", "3/5 tests passed". A count in front of the word is a runner's tally, no claim.
STAT_RE = re.compile(r"\b\d+(?:/\d+)?\s+(?:[a-z-]+\s+)?(?:passed|passes|green|clean)\b", re.I)
REDIRECT_RE = re.compile(r"^(?:\d*[<>]|&>)")
PASS_RE = re.compile(r"^PASS (.+) \(\d+(?:\.\d+)?s\)\s*$")
FAIL_RE = re.compile(r"^FAIL (.+?) rc=\d+")
SKIP_RE = re.compile(r"^SKIP (.+?), \d+ skipped \(")
LINE_FORMS = (("PASS", PASS_RE), ("FAIL", FAIL_RE), ("SKIP", SKIP_RE))


def _negates(token):
    return token in NEGATIONS or token.endswith(("n't", "n’t"))


def _sentence_claims(sentence):
    """True when one sentence says a check passed: a claim word, a check noun beside it, and none of the exempt forms
    (a negation or a condition just before, a named speaker just before, a statistic)."""
    tokens = TOKEN_RE.findall(STAT_RE.sub(" ", sentence.lower()))
    for at, word in enumerate(tokens):
        if word not in CLAIM_WORDS:
            continue
        before = tokens[max(0, at - NOUN_GAP):at]
        after = tokens[at + 1:at + 1 + NOUN_GAP] if word in ADJECTIVES else []
        if not any(t in CHECK_NOUNS for t in before + after):
            continue
        if any(_negates(t) or t in CONDITIONS for t in tokens[max(0, at - CUE_GAP):at]):
            continue
        if any(t in ATTRIBUTIONS for t in tokens[max(0, at - ATTRIBUTION_GAP):at]):
            continue
        return True
    return False


def claim_in(text):
    """The first sentence of `text` that says a check passed, else ''. Text in backticks or a fence, and a
    question, are no claim."""
    text = CODE_SPAN_RE.sub(" ", FENCE_RE.sub(" ", text))
    for sentence in SENTENCE_RE.split(text):
        sentence = sentence.strip()
        if sentence and not sentence.endswith("?") and _sentence_claims(sentence):
            return sentence
    return ""


def verdict_commands(command):
    """The command texts that `verdict` runs in one shell command: the words after the verdict word, as bin/verdict
    joins them into the name of its PASS line. The shell parser is guard_core's, the verdict words guard_stream's."""
    from guard_core import basename, resolve_command, segment_tokens, split_segments, strip_heredoc_bodies
    from guard_stream import VERDICT_WORDS
    ran = []
    for segment in split_segments(strip_heredoc_bodies(command)):
        tokens = segment_tokens(segment)
        at = resolve_command(tokens) if tokens else None
        if at is None:
            continue
        word = next((i for i in range(at) if basename(tokens[i].lstrip("(")) in VERDICT_WORDS), None)
        if word is None:
            continue
        argv = []
        for token in tokens[word + 1:]:
            if REDIRECT_RE.match(token):
                break
            argv.append(token)
        if argv:
            ran.append(" ".join(argv))
    return ran


def _result_text(content):
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


def cited(records):
    """True when some command's newest verdict line, in a non-sidechain Bash call's result, is a PASS."""
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
                        if found and found.group(1) in ran:
                            status[found.group(1)] = kind
    return "PASS" in status.values()


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


def problem(text, records):
    """The claiming sentence (cut to 120 characters) when `text` claims a pass that `records` do not cite, else ''."""
    claim = claim_in(text)
    return claim[:120] if claim and not cited(records) else ""


def send_problem(message, transcript_path):
    """`problem` for an outgoing message, reading the transcript at `transcript_path` only when the message claims.
    Fails open: an error, or no transcript to read, lets the message through with one stderr line."""
    try:
        if not isinstance(message, str):
            return ""
        claim = claim_in(message)
        if not claim:
            return ""
        if not isinstance(transcript_path, str) or not transcript_path:
            print("pass-claim guard failed open: no transcript to read", file=sys.stderr)
            return ""
        return "" if cited(_read(transcript_path)) else claim[:120]
    except Exception as exc:
        print("pass-claim guard failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return ""
