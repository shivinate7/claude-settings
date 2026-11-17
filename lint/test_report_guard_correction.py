#!/usr/bin/env python3
"""Every Stop refusal of a reply tells the session to post only the missing or corrected line, never to resend it.

Owner ruling R10 (inbox fb-1544-5, decision guard-remedy-not-to-owner): after any hook refusal of a reply, the session
posts only the short correction and never resends the reply, and every refusal text says so. The breach it stops:
the Departs-from and Recovered refusals named only what was missing, so the session resent the whole report.

The table is the refusal fixtures of lint/test_report_guard_remedy.py (its FIXTURES tuple, one home). Each runs through
report_guard as the Stop hook, through that suite's refusal_for(). The printed reason must tell the session to post only
the missing or corrected line and not to resend the reply, and it must carry the one shared correction tail,
report_guard.CORRECTION_TAIL. A refusal that builds its own text fails the second assert. A missing report asks for the
report itself, so it is left out of the table and gets no tail (owner, 2026-11-17 09:30 CST). Its own case pins that.

Not run one by one: the Unvetted "the check failed" text (only an exception reaches it), and the departs and hand-off
misses the remedy suite does not fixture. Each of those reaches the Stop join, where the reasons are joined, so the
fixtures of its check cover the join.

Controls pin the wording detector on fixed sentences, so a detector that flags nothing cannot pass the table.

The triage hold on a rewrite ends with the same line (TriageRewriteHoldTail, on the stalled suite's fixture). The
source scan (StopBlockEmitRouting) reads each Stop hook that settings.json registers, and fails a block that a hook
prints without report_guard.emit_stop. Its controls run on fixed sources.

Run it as:

    python3 lint/test_report_guard_correction.py -v
"""
import ast
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HOOKS = os.path.join(HERE, "..", "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
import report_guard as RG  # noqa: E402  the one home of the shared correction tail, CORRECTION_TAIL
import test_report_guard as trg  # noqa: E402  the module setup and teardown of the guard suite (one home)
import test_report_guard_remedy as trr  # noqa: E402  the refusal fixtures and the Stop runner (one home)
import test_report_guard_stalled as trs  # noqa: E402  the triage hold's fixture and its held() expectation (one home)

# The ruling's wording: post only the missing or corrected line, and never resend the reply.
POST_ONLY = re.compile(r"\bpost only\b", re.IGNORECASE)
MISSING_OR_CORRECTED = re.compile(r"\b(?:missing|corrected|correction)\b", re.IGNORECASE)
NO_RESEND = re.compile(r"\b(?:never|do not|don't)\s+(?:re-?send|send|write|repeat|post)\b[^.;]*?\b(?:reply|report)\b",
                       re.IGNORECASE)
# Refusals that carry the tail. A missing report gets none: it asks for the report (owner, 2026-11-17 09:30 CST).
TABLE = tuple(name for name in trr.FIXTURES if name != "missing_report")


def tells_correction_only(text):
    """True when `text` holds all three parts: post only, the missing or corrected line, and a negated resend."""
    return bool(POST_ONLY.search(text) and MISSING_OR_CORRECTED.search(text) and NO_RESEND.search(text))


def setUpModule():
    trg.setUpModule()  # the config isolation, the model stub and the run folder, as the guard suite sets them


def tearDownModule():
    trg.tearDownModule()  # the repo fixtures stay: the remedy suite removes them at its own teardown


class CorrectionTailTable(unittest.TestCase):
    def setUp(self):
        # A RemedyReasons instance only supplies its fixtures and Stop runner; its own test methods do not run here.
        self.helper = trr.RemedyReasons("test_2_clean_report_is_not_blocked")

    def test_every_stop_refusal_of_a_reply_says_post_only_the_correction(self):
        tail = getattr(RG, "CORRECTION_TAIL", "")
        for name in TABLE:
            with self.subTest(refusal=name):
                reason, _ = self.helper.refusal_for(name)  # asserts the refusal fires
                self.assertTrue(tells_correction_only(reason),
                                "refusal %s does not tell the session to post only the missing or corrected line "
                                "and never resend the reply: %r" % (name, reason))
                self.assertTrue(tail, "report_guard holds no shared CORRECTION_TAIL constant")
                self.assertIn(tail, reason,
                              "refusal %s builds its text without the shared CORRECTION_TAIL: %r" % (name, reason))

    def test_missing_report_refusal_has_no_correction_tail(self):
        tail = getattr(RG, "CORRECTION_TAIL", "")
        self.assertTrue(tail, "report_guard holds no shared CORRECTION_TAIL constant")
        reason, _ = self.helper.refusal_for("missing_report")  # asserts the refusal fires
        self.assertNotIn(tail, reason,
                         "the missing-report refusal carries the correction tail, but it asks for the report itself: %r"
                         % reason)


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


class TriageRewriteHoldTail(trs.StalledFixture, unittest.TestCase):
    """The triage hold on a rewrite, with no other problem in the reply, ends with the shared line. The ruling covers a
    triage hold on a rewrite too (owner, 2026-11-17 09:30 CST)."""

    def test_rewrite_hold_with_no_other_problem_says_post_only_the_correction(self):
        out = self.run_stop(self.stalled_wake() + [trs.assistant_text("Build read.")], stop_active=True)
        self.held(out, "build-stalled-check")  # the scope: the rewrite is held on the newest build's stalled step
        self.assertTrue(tells_correction_only(out["reason"]),
                        "the rewrite's triage hold does not tell the session to post only the correction and never "
                        "resend the reply: %r" % (out["reason"],))
        tail = getattr(RG, "CORRECTION_TAIL", "")
        self.assertTrue(bool(tail) and out["reason"].endswith(tail),
                        "the rewrite's triage hold does not end with report_guard.CORRECTION_TAIL: %r"
                        % (out["reason"],))


# --------------------------------------------------------------------------- the Stop block routing (source scan)
#
# A reply block reaches the owner through report_guard.emit_stop, the one emitter, so it carries the shared line.
# The scan reads each Stop hook that settings.json registers and parses it with ast. A comment or a string that holds
# a block is no call, so it is never read as a print.

EMIT_FILE = "lint/report_guard.py"  # the file that holds the one emitter of the Stop output
EMIT_FUNC = "emit_stop"  # the only function that may print a block
SCRIPT_OF_COMMAND = re.compile(r'/((?:hooks|lint)/[\w.-]+\.py)"')  # the script a Stop command runs, per settings.json

# Stop hooks whose block refuses no reply, so the scan does not read them. Each names its decision.
NON_REPLY_BLOCKS = {
    "hooks/ruling_home.py": "a missing rulings home, not a reply (decision memory-is-never-a-rulings-only-home)",
    "hooks/reread_check.py": "a reread after a compaction, not a reply (decision precompact-handoff, items 9 and 16)",
    "hooks/precompact_handoff.py": "a handoff rewrite after a compaction, not a reply (decision precompact-handoff)",
}


def source(*lines):
    """A Python source text of `lines`, with a final newline."""
    return "\n".join(lines) + "\n"


def stop_scripts(root):
    """The repo path of each Stop hook that settings.json registers, such as hooks/stall_watch.py."""
    with open(os.path.join(root, "settings.json"), encoding="utf-8") as handle:
        groups = json.load(handle)["hooks"]["Stop"]
    scripts = []
    for group in groups:
        for hook in group.get("hooks", []):
            found = SCRIPT_OF_COMMAND.search(hook.get("command", ""))
            if found:
                scripts.append(found.group(1))
    return scripts


def _is_name(node, name):
    return isinstance(node, ast.Name) and node.id == name


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def _dumped_payload(call):
    """X of print(json.dumps(X)) or sys.stdout.write(json.dumps(X)), else None. A print to stderr is no hook output."""
    func = call.func
    is_print = _is_name(func, "print")
    is_write = (isinstance(func, ast.Attribute) and func.attr == "write" and isinstance(func.value, ast.Attribute)
                and func.value.attr == "stdout" and _is_name(func.value.value, "sys"))
    if not (is_print or is_write) or not call.args or any(kw.arg == "file" for kw in call.keywords):
        return None
    dumped = call.args[0]
    if (isinstance(dumped, ast.Call) and isinstance(dumped.func, ast.Attribute) and dumped.func.attr == "dumps"
            and _is_name(dumped.func.value, "json") and dumped.args):
        return dumped.args[0]
    return None


def _sinks(tree):
    """(line, scope, payload) for each JSON output call in `tree`. The scope is the def that holds the call, or the
    module."""
    found = []

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                payload = _dumped_payload(child)
                if payload is not None:
                    found.append((child.lineno, scope, payload))
            inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            visit(child, inner)

    visit(tree, tree)
    return found


def _holds_block(node):
    """True when `node` holds a decision of "block": a dict entry "decision": "block", or a decision="block" keyword."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Dict) and any(_const(k) == "decision" and _const(v) == "block"
                                             for k, v in zip(sub.keys, sub.values)):
            return True
        if isinstance(sub, ast.Call) and any(kw.arg == "decision" and _const(kw.value) == "block"
                                             for kw in sub.keywords):
            return True
    return False


def _name_holds_block(scope, name):
    """True when a statement in `scope` sets the decision of `name` to "block": an assignment of a block value, a
    subscript store out["decision"] = "block", or name.update(decision="block")."""
    for sub in ast.walk(scope):
        if isinstance(sub, ast.Assign):
            if any(_is_name(t, name) for t in sub.targets) and _holds_block(sub.value):
                return True
            if (any(isinstance(t, ast.Subscript) and _is_name(t.value, name) and _const(t.slice) == "decision"
                    for t in sub.targets) and _const(sub.value) == "block"):
                return True
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "update"
                and _is_name(sub.func.value, name)
                and any(kw.arg == "decision" and _const(kw.value) == "block" for kw in sub.keywords)):
            return True
    return False


def bypass_lines(rel, text):
    """The lines of `text`, the source of the repo file `rel`, that print a block outside the emitter."""
    lines = []
    for line, scope, payload in _sinks(ast.parse(text, filename=rel)):
        if rel == EMIT_FILE and getattr(scope, "name", "") == EMIT_FUNC:
            continue
        blocked = _name_holds_block(scope, payload.id) if isinstance(payload, ast.Name) else _holds_block(payload)
        if blocked:
            lines.append(line)
    return lines


HAND_PRINTED = source("import json", "", "def stop():",
                      "    print(json.dumps({\"decision\": \"block\", \"reason\": \"x\"}))")  # line 4
BUILT_BY_UPDATE = source("import json", "", "def stop():", "    out = {}",
                         "    out.update(decision=\"block\", reason=\"x\")", "    print(json.dumps(out))")  # line 6
STORED_BY_SUBSCRIPT = source("import json", "import sys", "", "def stop():", "    out = {}",
                             "    out[\"decision\"] = \"block\"", "    sys.stdout.write(json.dumps(out))")  # line 7
ROUTED = source("import json", "", "def emit_stop(payload):", "    print(json.dumps(payload))", "", "def note():",
                "    print(json.dumps({\"systemMessage\": \"x\"}))", "", "def route():",
                "    emit_stop({\"decision\": \"block\", \"reason\": \"x\"})")  # no line: emit_stop is the route
EMITTER_ONLY = source("import json", "", "def emit_stop(payload):", "    print(json.dumps({\"decision\": \"block\"}))")
IN_STRINGS_AND_COMMENTS = source("import json", "# print(json.dumps({\"decision\": \"block\"}))",
                                 "TEXT = \"print(json.dumps({'decision': 'block'}))\"", "DOC = \"\"\"",
                                 "print(json.dumps({\"decision\": \"block\"}))", "Don't stop here.", "\"\"\"")
HASH_IN_A_BLOCK = source("import json", "", "def stop():",
                         "    print(json.dumps({\"decision\": \"block\", \"reason\": \"see # and /* here, don't stop\"}))")

FULL_SIZE_BODY = ["x%d = %d" % (k, k) for k in range(3000)]
FULL_SIZE = source(*FULL_SIZE_BODY, "import json", "print(json.dumps({\"decision\": \"block\"}))")  # line 3002


class StopBlockEmitRouting(unittest.TestCase):
    def test_every_reply_block_of_a_stop_hook_prints_through_emit_stop(self):
        stops = stop_scripts(REPO)
        # Scope first: the scan reads the Stop hooks settings.json registers, and each exemption must be one of them.
        self.assertIn(EMIT_FILE, stops, "settings.json registers no Stop hook at %s" % EMIT_FILE)
        self.assertIn("hooks/feedback_guard.py", stops,
                      "settings.json registers no Stop hook at hooks/feedback_guard.py")
        self.assertEqual(sorted(set(NON_REPLY_BLOCKS) - set(stops)), [],
                         "an exempt Stop hook is no longer registered in settings.json")
        bypasses = []
        for rel in stops:
            if rel in NON_REPLY_BLOCKS:
                continue
            with open(os.path.join(REPO, rel), encoding="utf-8") as handle:
                bypasses += ["%s:%d" % (rel, line) for line in bypass_lines(rel, handle.read())]
        self.assertEqual(bypasses, [], "a Stop block prints outside report_guard.emit_stop: %s" % ", ".join(bypasses))


class StopBlockScanControls(unittest.TestCase):
    # Green on the old code: they test the scan on fixed sources, not on the repo.
    def test_control_a_block_printed_by_hand_is_read(self):
        self.assertEqual(bypass_lines("hooks/x.py", HAND_PRINTED), [4], "control: a hand-printed block is not read")

    def test_control_a_block_built_by_update_is_read(self):
        self.assertEqual(bypass_lines("hooks/x.py", BUILT_BY_UPDATE), [6],
                         "control: a block built by update is not read")

    def test_control_a_block_stored_by_subscript_is_read(self):
        self.assertEqual(bypass_lines("hooks/x.py", STORED_BY_SUBSCRIPT), [7],
                         "control: a block stored by subscript is not read")

    def test_control_a_block_handed_to_emit_stop_and_a_note_are_no_print(self):
        self.assertEqual(bypass_lines("hooks/x.py", ROUTED), [], "control: a route or a note reads as a bypass")

    def test_control_only_report_guards_emit_stop_is_exempt(self):
        self.assertEqual(bypass_lines("hooks/x.py", EMITTER_ONLY), [4],
                         "control: a block printed in an emit_stop of another file is exempt")
        self.assertEqual(bypass_lines(EMIT_FILE, EMITTER_ONLY), [], "control: report_guard's emit_stop is not exempt")

    def test_control_block_text_in_a_string_or_comment_is_no_print(self):
        self.assertEqual(bypass_lines("hooks/x.py", IN_STRINGS_AND_COMMENTS), [],
                         "control: a block in a string, a comment or a multi-line string reads as a print")

    def test_control_a_hash_or_quote_inside_a_real_block_is_still_read(self):
        self.assertEqual(bypass_lines("hooks/x.py", HASH_IN_A_BLOCK), [4],
                         "control: a block whose reason holds a comment opener is not read")

    def test_control_empty_and_full_size_sources(self):
        self.assertEqual(bypass_lines("hooks/x.py", source()), [], "control: an empty source reads as a bypass")
        self.assertEqual(bypass_lines("hooks/x.py", FULL_SIZE), [len(FULL_SIZE_BODY) + 2],
                         "control: a block at the end of a full-size source is not read")


if __name__ == "__main__":
    unittest.main()
