#!/usr/bin/env python3
"""The PreToolUse matcher that routes to hooks/guard.py must cover every tool the guard judges.
Run: python3 lint/test_settings_matcher.py. Without Workflow and start_session in the matcher,
the guard's subagent-model-floor never sees those calls.
"""
import json, os, re, subprocess, sys, unittest

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


# The Agent judge's Explore clause as settings.json carries it, whitespace folded to single spaces.
EXPLORE_CLAUSE = ("and the call's model field is neither sonnet nor opus (haiku, or no model field, blocks; "
                  "text in the brief does not count); the fix is model sonnet or opus with effort high")


def explore_clause_pinned(text):
    """True when the clause sits inside the Explore rule: from 'For an Explore spawn,' to 'Otherwise answer'."""
    found = re.search(r"For an Explore spawn,(.*?)Otherwise answer", text)
    return bool(found) and EXPLORE_CLAUSE in found.group(1)


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

    def agent_prompt(self):
        hooks = [h for e in pre_tool_entries() if e.get("matcher") == "Agent" for h in e["hooks"]
                 if h.get("type") == "prompt"]
        self.assertEqual(len(hooks), 1)
        return " ".join(hooks[0]["prompt"].split())

    def test_explore_rule_passes_sonnet_and_opus(self):
        # The floor is Sonnet; the owner's "use opus" must pass (subagent-model-cap, audit Explore row).
        # A word pin ("opus" appears) also holds for a reversed clause, so the pin is the whole clause.
        self.assertIn(EXPLORE_CLAUSE, self.agent_prompt(),
                      "the Agent judge's Explore clause is not the pinned text: opus or sonnet may block")

    def test_explore_rule_still_blocks_haiku_or_unset(self):
        self.assertTrue(explore_clause_pinned(self.agent_prompt()),
                        "the pinned clause is not inside the Explore rule: haiku or no model may pass")

    def test_explore_clause_mutants_fail_the_pin(self):
        # Each mutant is the real row text with the clause changed in memory. The pin must refuse all.
        text = self.agent_prompt()
        self.assertTrue(explore_clause_pinned(text), "no pinned clause in the row: nothing to mutate")
        mutants = {
            "reversed": "and the call sets model opus (a haiku or no model passes; text in the brief does not "
                        "count); the fix is model sonnet or opus with effort high",
            "haiku passes": EXPLORE_CLAUSE.replace("(haiku, or no model field, blocks;",
                                                   "(haiku passes, no model field blocks;"),
            "brief text counts": EXPLORE_CLAUSE.replace("; text in the brief does not count", ""),
        }
        for name, clause in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(clause, EXPLORE_CLAUSE, "the mutant did not change the clause")
                mutated = text.replace(EXPLORE_CLAUSE, clause)
                self.assertNotEqual(mutated, text)
                self.assertFalse(explore_clause_pinned(mutated), "the pin passes the %s mutant" % name)

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
    "stall_watch.py", "report_gate.py", "config_watch.py", "ruling_home.py",
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


# Mods reach each machine only through the marketplace (decision mods-install-via-marketplace). A
# third-party marketplace never refreshes unless autoUpdate is true, so without it a mod stays at the
# copy fetched on the first install.
class ModsAutoUpdate(unittest.TestCase):
    def test_claude_settings_marketplace_auto_updates(self):
        with open(SETTINGS, encoding="utf-8") as f:
            entry = json.load(f)["extraKnownMarketplaces"]["claude-settings"]
        self.assertEqual(entry["source"], {"source": "github", "repo": "shivinate7/claude-settings"})
        self.assertIs(entry.get("autoUpdate"), True)


# The question reviewer: ONE agent hook on PreToolUse AskUserQuestion, model
# pinned to an Opus id, the rubric in the hook prompt. It replaces the prompt judge and
# hooks/question_outcome.py. A failed or timed-out agent hook lets the question through, so no code
# gate backs the rubric: the prompt text is the only home of it, and these cases pin that text.
# An agent hook takes only these keys (probed on Claude Code 2.1.296 on Windows). The prompt
# hooks beside it carry `continueOnBlock`, which is not one of them.
AGENT_HOOK_KEYS = {"type", "prompt", "if", "timeout", "model", "statusMessage", "once"}
OPUS_PREFIX = "claude-opus-"
# Each rubric item the prompt must name, with the patterns that must all match the prompt. The prompt is
# whitespace-folded and matched without case, except the three labels, which match as written.
GOAL, PROBLEM, BASED = "(?-i:Goal:)", "(?-i:Problem:)", "(?-i:Based on:)"
RUBRIC = {
    "Goal line first": [GOAL, GOAL + r".{0,100}\bfirst\b|\bfirst\b.{0,100}" + GOAL],
    "Problem line": [PROBLEM],
    "option says gain and lose": [r"\bgains?\b", r"\blos(?:e|es|ing|s)\b"],
    "recommendation": [r"\brecommend"],
    "no unexplained ids": [r"\bunexplained\b.{0,40}\b(?:ids?|names?|identifiers?)\b"
                           r"|\b(?:ids?|identifiers?)\b.{0,80}\b(?:(?:un)?explain\w*|(?:un)?gloss\w*|plain)\b"],
    "Based on: lines with source kind": [BASED, r"\bsource[- ]kind\b|\bkind of source\b"
                                                r"|\bsource\b.{0,60}\bkind\b|\bkind\b.{0,60}\bsource\b"],
}
# One sentence per item: a prompt that meets the rubric, and the mutants the check must see.
SAMPLE = {
    "Goal line first": "The box opens with a Goal: line first.",
    "Problem line": "Then a Problem: line.",
    "option says gain and lose": "Each option says what the owner would gain and lose.",
    "recommendation": "The box carries a recommendation.",
    "no unexplained ids": "Reject unexplained ids.",
    "Based on: lines with source kind": "Premises show as Based on: lines, each with its source kind.",
}


def rubric_gaps(prompt):
    """The rubric items the prompt does not name, in RUBRIC order."""
    text = " ".join(prompt.split())
    return [item for item, pats in RUBRIC.items() if not all(re.search(p, text, re.I) for p in pats)]


# The hook prompt cannot point at docs/decisions/, so it lists the premise kinds itself: a second copy of
# the kinds table in docs/decisions/premise-format.md. These cases keep the copy equal to the table.
# PREMISE_FORMAT_UNDER_TEST points the test at another copy of the table, as SETTINGS_UNDER_TEST does.
PREMISE_FORMAT = os.environ.get("PREMISE_FORMAT_UNDER_TEST") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs", "decisions", "premise-format.md")
KIND_ROW = re.compile(r"^\|\s*`([a-z]+)`\s*\|", re.M)
KIND_LIST = re.compile(r"\bsource kinds?:\s*([a-z, ]+?)\s*(?:[(.;]|$)")


def table_kinds(text):
    """The kinds of the premise table: the backticked first cell of each row, in table order."""
    return KIND_ROW.findall(text)


def prompt_kinds(prompt):
    """The kinds the hook prompt lists after 'source kind:', in prompt order; [] when it lists none."""
    found = KIND_LIST.search(" ".join(prompt.split()))
    return [k for k in re.split(r"\s*,\s*|\s+or\s+", found.group(1)) if k] if found else []


class QuestionReviewer(unittest.TestCase):
    def ask_hooks(self):
        return [h for e in pre_tool_entries() if covers(e, "AskUserQuestion") for h in e["hooks"]]

    def agent_hook(self):
        agents = [h for h in self.ask_hooks() if h.get("type") == "agent"]
        self.assertEqual(len(agents), 1, "want one agent hook on AskUserQuestion, found %d" % len(agents))
        return agents[0]

    def test_ask_user_question_runs_one_hook_and_it_is_an_agent(self):
        types = [h.get("type") for h in self.ask_hooks()]
        self.assertEqual(types, ["agent"], "AskUserQuestion hooks are %s, want one agent hook" % types)

    def test_agent_hook_pins_an_opus_id(self):
        model = self.agent_hook().get("model")
        self.assertTrue(isinstance(model, str) and model.startswith(OPUS_PREFIX),
                        "agent hook model is %r, want a full id starting %s" % (model, OPUS_PREFIX))

    def test_agent_hook_uses_only_agent_hook_keys(self):
        extra = sorted(set(self.agent_hook()) - AGENT_HOOK_KEYS)
        self.assertEqual(extra, [], "keys outside the agent-hook schema: %s" % extra)

    def test_agent_hook_prompt_names_every_rubric_item(self):
        gaps = rubric_gaps(self.agent_hook().get("prompt") or "")
        self.assertEqual(gaps, [], "the agent hook prompt does not name: %s" % gaps)

    def test_the_rubric_check_sees_each_missing_item(self):
        # Green on main by design: it tests the check, not settings.json.
        self.assertEqual(set(SAMPLE), set(RUBRIC), "SAMPLE and RUBRIC name different items")
        self.assertEqual(rubric_gaps(" ".join(SAMPLE.values())), [])
        self.assertEqual(rubric_gaps(""), list(RUBRIC))
        for item in RUBRIC:
            with self.subTest(dropped=item):
                rest = " ".join(v for k, v in SAMPLE.items() if k != item)
                self.assertEqual(rubric_gaps(rest), [item])

    def test_agent_hook_prompt_lists_the_kinds_of_the_premise_table(self):
        with open(PREMISE_FORMAT, encoding="utf-8") as f:
            table = table_kinds(f.read())
        self.assertTrue(table, "no kind rows in %s" % PREMISE_FORMAT)
        listed = prompt_kinds(self.agent_hook().get("prompt") or "")
        self.assertTrue(listed, "the agent hook prompt lists no source kinds after 'source kind:'")
        self.assertEqual(sorted(listed), sorted(table),
                         "hook prompt kinds %s, premise table kinds %s: update the one that drifted" % (listed, table))

    def test_the_kinds_readers_see_a_kind_added_or_dropped(self):
        # Green on main by design: it tests the two readers, not settings.json.
        row = "| `%s` | means | Weak |\n"
        table = table_kinds("| Kind | Means |\n|---|---|\n" + row % "ruling" + row % "assumed")
        self.assertEqual(table, ["ruling", "assumed"])
        self.assertEqual(prompt_kinds("each with its source kind: ruling or assumed (see the table)"), table)
        self.assertEqual(prompt_kinds("its source kind: ruling, measured, assumed."), ["ruling", "measured", "assumed"])
        self.assertEqual(prompt_kinds("no list here"), [])
        self.assertEqual(table_kinds("prose with `ruling` in it\n"), [])

    def test_no_hook_runs_question_outcome(self):
        with open(SETTINGS, encoding="utf-8") as f:
            events = json.load(f)["hooks"]
        found = sorted(ev for ev, entries in events.items() if "question_outcome" in json.dumps(entries))
        self.assertEqual(found, [], "a hook still names question_outcome under: %s" % found)

    def test_question_outcome_script_is_a_stub(self):
        # A running session may still call it, so it stays as an exit-0 stub (lint/check_hook_stubs.py).
        script = os.path.join(os.path.dirname(SETTINGS), "hooks", "question_outcome.py")
        r = subprocess.run([sys.executable, script], input='{"tool_name": "AskUserQuestion"}',
                           capture_output=True, text=True, timeout=30)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""),
                         "hooks/question_outcome.py must exit 0 and print nothing")


# The STE write gate and the markdown sweep are not wired in settings.json.
# CI's STE lint (actions/ste-lint) carries STE001, STE011 and STE013 on changed lines instead.
class SteHooksRemoved(unittest.TestCase):
    def test_no_hook_runs_the_removed_scripts(self):
        with open(SETTINGS, encoding="utf-8") as f:
            events = json.load(f)["hooks"]
        for script in ("ste_gate.py", "md_sweep.py"):
            with self.subTest(script=script):
                wired = ["%s %s" % (event, entry.get("matcher", "*"))
                         for event, entries in events.items() for entry in entries
                         if script in [n for c in command_rows([entry]) for n in script_names(c)]]
                self.assertEqual(wired, [], "%s is still wired in settings.json" % script)

    def test_the_guard_and_the_question_check_still_gate_pre_tool_use(self):
        # The two command gates stay: hooks/test_wrappers.py pins that each one fails closed. The question
        # check is one agent hook, so it is matched by type and by its matcher, not by a script name.
        with open(SETTINGS, encoding="utf-8") as f:
            pre = json.load(f)["hooks"]["PreToolUse"]
        names = [n for c in command_rows(pre) for n in script_names(c)]
        self.assertIn("guard.py", names)
        agent_entries = [e for e in pre if any(h.get("type") == "agent" for h in e.get("hooks", []))]
        covered = [e for e in agent_entries if "AskUserQuestion" in e.get("matcher", "").split("|")]
        self.assertTrue(covered, "no PreToolUse agent hook has AskUserQuestion in its matcher")


# The SendMessage judges must see the receiver's busy state and the override pass. A prompt hook
# sees only its tool input (to, summary, message), so both are read by code: a command hook.
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
# (docs/decisions/subagent-model-cap.md), and that row's model must equal the hook's model.
RECORD = os.path.join(os.path.dirname(SETTINGS), "docs", "decisions", "subagent-model-cap.md")
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

    def test_check_goes_red_when_the_agent_row_is_missing(self):
        # Mutation: take Agent out of the judge row. The check must name it.
        self.assertTrue(any("Agent" in re.findall(r"[A-Za-z]+", r[0]) for r in judge_rows(self.text)),
                        "the judge row changed; update this mutation")
        mutated = "\n".join(l.replace("Agent", "") if JUDGE_ROW in l else l for l in self.text.splitlines())
        gaps = table_gaps(mutated, list(judge_hooks()))
        self.assertTrue(any(g.startswith("Agent:") for g in gaps), gaps)


if __name__ == "__main__":
    unittest.main()
