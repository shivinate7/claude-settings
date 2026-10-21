#!/usr/bin/env python3
"""The PreToolUse matcher that routes to hooks/guard.py must cover every tool the guard judges.
Run: python3 lint/test_settings_matcher.py. Without Workflow and start_session in the matcher,
the guard's subagent-model-floor never sees those calls.
"""
import json, os, re, unittest

SETTINGS = os.environ.get("SETTINGS_UNDER_TEST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings.json")


def guard_matchers():
    entries = json.load(open(SETTINGS))["hooks"]["PreToolUse"]
    return [e["matcher"] for e in entries
            if any("guard.py" in h.get("command", "") for h in e["hooks"])]


class Matcher(unittest.TestCase):
    def test_guard_matcher_covers_model_floor_tools(self):
        matchers = guard_matchers()
        self.assertTrue(matchers)
        for tool in ("Agent", "Task", "Workflow", "mcp__ccd_session__start_session"):
            with self.subTest(tool=tool):
                self.assertTrue(any(re.fullmatch(m, tool) for m in matchers))


# The prose judge: ONE command hook on Edit and Write. It decides by path, in code, and calls the
# model only for Markdown and decision records. No prompt hook may sit on Edit or Write: it would call a
# model on every .ts, .tsx and .json edit.
def pre_tool_entries():
    with open(SETTINGS, encoding="utf-8") as f:
        return json.load(f)["hooks"]["PreToolUse"]


def covers(entry, tool):
    return re.fullmatch(entry.get("matcher", ""), tool) is not None


class ProseJudgeRow(unittest.TestCase):
    def test_no_prompt_or_agent_hook_on_edit_or_write(self):
        for tool in ("Edit", "Write"):
            with self.subTest(tool=tool):
                bad = [h.get("type") for e in pre_tool_entries() if covers(e, tool)
                       for h in e["hooks"] if h.get("type") in JUDGE_TYPES]
                self.assertEqual(bad, [], "a model-judge hook still runs on every %s" % tool)

    def test_one_prose_judge_command_hook_covers_edit_and_write(self):
        rows = [(e, h) for e in pre_tool_entries() for h in e["hooks"]
                if h.get("type") == "command" and "prose_judge.py" in script_names(h.get("command", ""))]
        self.assertEqual(len(rows), 1, "want one prose_judge.py command hook, found %d" % len(rows))
        entry, hook = rows[0]
        for tool in ("Edit", "Write"):
            self.assertTrue(covers(entry, tool), "prose_judge.py does not run on %s" % tool)
        self.assertFalse(covers(entry, "AskUserQuestion"))
        self.assertGreater(hook.get("timeout", 0), 0)

    def test_agent_judge_stays(self):
        hooks = [h for e in pre_tool_entries() if e.get("matcher") == "Agent" for h in e["hooks"]]
        self.assertTrue(any(h.get("type") == "prompt" for h in hooks), "Agent prompt judge missing")


# A prompt or agent hook names its model. The evaluator rejects the bare alias "haiku" (stderr
# unrecognized_model, query_source hook_prompt), so each judge would fail and let calls through.
# A full id starts with "claude-".
JUDGE_TYPES = ("prompt", "agent")


def judge_hooks():
    """Yield (label, hook) for every prompt or agent hook in settings.json, under any event."""
    with open(SETTINGS, encoding="utf-8") as f:
        events = json.load(f)["hooks"]
    for event, entries in events.items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                if hook.get("type") in JUDGE_TYPES:
                    label = event
                    if "matcher" in entry:
                        label += " matcher=" + entry["matcher"]
                    if "if" in hook:
                        label += " if=" + hook["if"]
                    yield label, hook


class JudgeModelIds(unittest.TestCase):
    def test_every_prompt_and_agent_hook_names_a_full_model_id(self):
        found, bad = 0, []
        for label, hook in judge_hooks():
            found += 1
            model = hook.get("model")
            if not (isinstance(model, str) and model.startswith("claude-")):
                bad.append("%s (%s) model=%r" % (label, hook["type"], model))
        if not found:
            self.fail("no prompt or agent hook found, so the scan proves nothing")
        if bad:
            self.fail("model is not a full id (must start claude-): " + "; ".join(bad))


# decision-watch runs as the mod (an enabled plugin), not as a Stop row. The reply judge and the
# AskUserQuestion check keep their own calls. The Stop rows are pinned by script name, not by index.
DECISION_WATCH_PLUGIN = "decision-watch@claude-settings"
STOP_SCRIPTS_AFTER_SWAP = sorted([
    "stall_watch.py", "report_gate.py", "md_sweep.py", "config_watch.py", "ruling_home.py",
    "precompact_handoff.py", "reply_judge.py", "feedback_gate.py", "reread_check.py",
])


def command_rows(entries):
    """Every command string under a list of hook entries."""
    return [h.get("command", "") for e in entries for h in e.get("hooks", []) if h.get("type") == "command"]


def script_names(command):
    """The hooks/ or lint/ script names a command assigns to g, e.g. decision_watch.py."""
    return re.findall(r'/(\w+\.py)(?=["\s]|$)', command)


def decision_watch_stop_rows(settings):
    """The Stop command rows that run decision_watch.py, quoted path or bare."""
    return [c for c in command_rows(settings["hooks"]["Stop"]) if "decision_watch.py" in script_names(c)]


class DecisionWatchSwap(unittest.TestCase):
    def setUp(self):
        with open(SETTINGS, encoding="utf-8") as f:
            self.settings = json.load(f)

    def test_decision_watch_plugin_is_enabled(self):
        self.assertIs(self.settings["enabledPlugins"].get(DECISION_WATCH_PLUGIN), True)

    def test_no_stop_row_runs_decision_watch(self):
        self.assertEqual(decision_watch_stop_rows(self.settings), [], "a Stop row still runs decision_watch.py")

    def test_stop_rows_are_the_others_only(self):
        names = sorted(n for c in command_rows(self.settings["hooks"]["Stop"]) for n in script_names(c))
        self.assertEqual(names, STOP_SCRIPTS_AFTER_SWAP)

    def test_reply_judge_stop_row_stays(self):
        names = [n for c in command_rows(self.settings["hooks"]["Stop"]) for n in script_names(c)]
        self.assertIn("reply_judge.py", names)

    def test_ask_user_question_rows_stay(self):
        entries = [e for e in self.settings["hooks"]["PreToolUse"] if e.get("matcher") == "AskUserQuestion"]
        hooks = [h for e in entries for h in e.get("hooks", [])]
        self.assertTrue(any(h.get("type") == "prompt" for h in hooks), "AskUserQuestion prompt judge missing")
        names = [n for c in command_rows(entries) for n in script_names(c)]
        self.assertIn("question_outcome.py", names)


# The SendMessage judge must see the receiver's busy state. A prompt hook sees only its tool
# input (to, summary, message), so the state has to be read by code: a command or agent hook.
# `claude agents --json` rows carry name, sessionId, status (busy, idle, waiting), cwd.
def pre_tool_hooks(matcher):
    return [h for e in json.load(open(SETTINGS))["hooks"]["PreToolUse"] if e["matcher"] == matcher
            for h in e["hooks"]]


class SendMessageJudge(unittest.TestCase):
    def test_sendmessage_has_a_hook_that_reads_receiver_state(self):
        hooks = pre_tool_hooks("SendMessage")
        self.assertTrue(hooks, "no PreToolUse hook on SendMessage")
        self.assertTrue(any(h.get("type") in ("command", "agent") for h in hooks),
                        "SendMessage has only prompt hooks, which cannot read the board's busy state")


# Every prompt or agent judge in settings.json must have a row in the model-per-role table
# (decisions/subagent-model-cap.md), and that row's model must equal the hook's model.
RECORD = os.path.join(os.path.dirname(SETTINGS), "decisions", "subagent-model-cap.md")
JUDGE_ROW = "prompt-hook judges"


def judge_rows(text):
    """Table rows whose first cell names the prompt-hook judges, as cell lists."""
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and JUDGE_ROW in cells[0]:
                rows.append(cells)
    return rows


def table_gaps(text, hooks):
    """One line per judge the table does not name, or names with another model."""
    rows = judge_rows(text)
    gaps = []
    for label, hook in hooks:
        m = re.search(r"matcher=(\S+)", label)
        name = m.group(1) if m else label
        named = [r for r in rows if name in re.findall(r"[A-Za-z]+", r[0])]
        model = hook.get("model") or ""
        if not named:
            gaps.append("%s: no model-table row names it" % name)
        elif not any(model and model in r[1] for r in named):
            gaps.append("%s: table model is not %s" % (name, model))
    return gaps


class JudgeModelRows(unittest.TestCase):
    def setUp(self):
        with open(RECORD, encoding="utf-8") as f:
            self.text = f.read()

    def test_every_prompt_or_agent_judge_has_a_row_with_its_model(self):
        hooks = list(judge_hooks())
        self.assertTrue(hooks, "no judge hook found, so the check proves nothing")
        self.assertEqual(table_gaps(self.text, hooks), [])

    def test_check_goes_red_when_the_sendmessage_row_is_missing(self):
        # Mutation: take SendMessage out of the judge row. The check must name it.
        self.assertTrue(any("SendMessage" in r[0] for r in judge_rows(self.text)), "the judge row changed; update this mutation")
        gaps = table_gaps(self.text.replace("SendMessage", ""), list(judge_hooks()))
        self.assertTrue(any(g.startswith("SendMessage:") for g in gaps), gaps)


if __name__ == "__main__":
    unittest.main()
