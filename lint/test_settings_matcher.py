#!/usr/bin/env python3
"""The PreToolUse matcher that routes to hooks/guard.py must cover every tool the guard judges.
Run: python3 lint/test_settings_matcher.py. Without Workflow and start_session in the matcher,
the guard's agent-model-floor never sees those calls.
"""
import json, os, re, subprocess, sys, unittest

SETTINGS = os.environ.get("SETTINGS_UNDER_TEST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings.json")

CALL_JUDGE = os.environ.get("CALL_JUDGE_UNDER_TEST") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "call_judge.py")


def call_judge_judges():
    """JUDGES of hooks/call_judge.py: tool name -> (prompt, model, timeout, rule, fallback). The Agent spawn
    judge and the AskUserQuestion reviewer live there, as one command hook, so an owner override can lift them.
    CALL_JUDGE_UNDER_TEST points the test at another copy (a red run on a wrong model constant)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("call_judge_under_test", CALL_JUDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.JUDGES)


def call_judge_entries():
    """The PreToolUse entries whose command hook runs call_judge.py."""
    with open(SETTINGS, encoding="utf-8") as f:
        pre = json.load(f)["hooks"]["PreToolUse"]
    return [(e, h) for e in pre for h in e["hooks"]
            if h.get("type") == "command" and "call_judge.py" in h.get("command", "")]


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

    def test_guard_matcher_covers_lane_effort_tool(self):
        # Rule lane-effort-pin reads the create_session call that starts a lane, so the guard must see it.
        matchers = guard_matchers()
        self.assertTrue(matchers)
        tool = "mcp__claude-code-remote__create_session"
        self.assertTrue(any(re.fullmatch(m, tool) for m in matchers),
                        "no guard matcher covers %s: %r" % (tool, matchers))

    def test_guard_matcher_covers_exit_worktree(self):
        # Rule session-home deletes a session's record on ExitWorktree, so the guard must see that call.
        matchers = guard_matchers()
        self.assertTrue(any(re.fullmatch(m, "ExitWorktree") for m in matchers),
                        "no guard matcher covers ExitWorktree: %r" % matchers)


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
        # The Agent spawn judge is a model call in hooks/call_judge.py, launched by one command hook that
        # covers Agent. It is no prompt hook now, because a prompt hook cannot read an owner override.
        rows = call_judge_entries()
        self.assertEqual(len(rows), 1, "want one call_judge.py command hook, found %d" % len(rows))
        self.assertTrue(covers(rows[0][0], "Agent"), "call_judge.py does not run on Agent")
        self.assertIn("Agent", call_judge_judges(), "call_judge.py holds no Agent judge")
        self.assertFalse([h for e in pre_tool_entries() if covers(e, "Agent") for h in e["hooks"]
                          if h.get("type") in JUDGE_TYPES], "a prompt or agent hook still runs on Agent")

    def agent_prompt(self):
        return " ".join(call_judge_judges()["Agent"][0].split())

    def test_explore_rule_passes_sonnet_and_opus(self):
        # The floor is Sonnet; the owner's "use opus" must pass (agent-model-cap, audit Explore row).
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
    def test_every_judge_names_a_full_model_id(self):
        # The judges' models live in hooks/call_judge.py now. Any prompt or agent hook that comes back to
        # settings.json is held to the same rule.
        found, bad = 0, []
        for tool, judge in call_judge_judges().items():
            found += 1
            model = judge[1]
            if not (isinstance(model, str) and model.startswith("claude-")):
                bad.append("call_judge.py %s model=%r" % (tool, model))
        for label, hook in judge_hooks():
            model = hook.get("model")
            if not (isinstance(model, str) and model.startswith("claude-")):
                bad.append("%s (%s) model=%r" % (label, hook["type"], model))
        if not found:
            self.fail("call_judge.py holds no judge, so the scan proves nothing")
        if bad:
            self.fail("model is not a full id (must start claude-): " + "; ".join(bad))

    def test_the_agent_judge_runs_sonnet(self):
        model = call_judge_judges()["Agent"][1]
        self.assertTrue(model.startswith("claude-sonnet-"), "the Agent spawn judge runs %r, want Sonnet" % model)


# decision-watch runs as the mod (an enabled plugin), not as a Stop row. The reply judge and the
# AskUserQuestion check keep their own calls. The Stop rows are pinned by script name, not by index.
DECISION_WATCH_PLUGIN = "decision-watch@claude-settings"
STOP_SCRIPTS_AFTER_SWAP = sorted([
    "stall_watch.py", "report_guard.py", "config_watch.py", "ruling_home.py",
    "precompact_handoff.py", "reply_judge.py", "feedback_guard.py", "reread_check.py",
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
# guard backs the rubric: the prompt text is the only home of it, and these cases pin that text.
# An agent hook takes only these keys (probed on Claude Code 2.1.296 on Windows). The prompt
# hooks beside it carry `continueOnBlock`, which is not one of them.
COMMAND_HOOK_KEYS = {"type", "command", "if", "timeout", "statusMessage", "once", "async"}
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

    def question_prompt(self):
        return call_judge_judges()["AskUserQuestion"][0]

    def test_ask_user_question_runs_one_hook_and_it_is_call_judge(self):
        # The reviewer is a model call in hooks/call_judge.py, launched by one command hook, so an owner
        # override can lift its refusal. No agent hook may come back: it reads no override.
        hooks = self.ask_hooks()
        self.assertEqual([h.get("type") for h in hooks], ["command"],
                         "AskUserQuestion hooks are %s, want one command hook" % [h.get("type") for h in hooks])
        self.assertIn("call_judge.py", script_names(hooks[0].get("command", "")))

    def test_the_reviewer_runs_an_opus_id(self):
        model = call_judge_judges()["AskUserQuestion"][1]
        self.assertTrue(isinstance(model, str) and model.startswith(OPUS_PREFIX),
                        "the question reviewer model is %r, want a full id starting %s" % (model, OPUS_PREFIX))

    def test_call_judge_hook_uses_only_command_hook_keys(self):
        # The models and prompts live in call_judge.py. A model or prompt key on the row would be dead text.
        (_, hook), = call_judge_entries()
        extra = sorted(set(hook) - COMMAND_HOOK_KEYS)
        self.assertEqual(extra, [], "keys outside the command-hook schema: %s" % extra)
        self.assertGreater(hook.get("timeout", 0), max(j[2] for j in call_judge_judges().values()),
                           "the hook timeout does not outlast the longest model call")

    def test_the_reviewer_prompt_names_every_rubric_item(self):
        gaps = rubric_gaps(self.question_prompt())
        self.assertEqual(gaps, [], "the question reviewer prompt does not name: %s" % gaps)

    def test_the_rubric_check_sees_each_missing_item(self):
        # Green on main by design: it tests the check, not settings.json.
        self.assertEqual(set(SAMPLE), set(RUBRIC), "SAMPLE and RUBRIC name different items")
        self.assertEqual(rubric_gaps(" ".join(SAMPLE.values())), [])
        self.assertEqual(rubric_gaps(""), list(RUBRIC))
        for item in RUBRIC:
            with self.subTest(dropped=item):
                rest = " ".join(v for k, v in SAMPLE.items() if k != item)
                self.assertEqual(rubric_gaps(rest), [item])

    def test_reviewer_prompt_lists_the_kinds_of_the_premise_table(self):
        with open(PREMISE_FORMAT, encoding="utf-8") as f:
            table = table_kinds(f.read())
        self.assertTrue(table, "no kind rows in %s" % PREMISE_FORMAT)
        listed = prompt_kinds(self.question_prompt())
        self.assertTrue(listed, "the question reviewer prompt lists no source kinds after 'source kind:'")
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


# The STE write guard and the markdown sweep are not wired in settings.json.
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

    def test_the_guard_and_the_question_check_still_guard_pre_tool_use(self):
        # The two command guards stay: hooks/test_wrappers.py pins that each one fails closed. The question
        # check is the call_judge.py command hook, matched by its script and its matcher.
        with open(SETTINGS, encoding="utf-8") as f:
            pre = json.load(f)["hooks"]["PreToolUse"]
        names = [n for c in command_rows(pre) for n in script_names(c)]
        self.assertIn("guard.py", names)
        covered = [e for e, _ in call_judge_entries() if "AskUserQuestion" in e.get("matcher", "").split("|")]
        self.assertTrue(covered, "no PreToolUse call_judge.py command hook has AskUserQuestion in its matcher")


# The SendMessage judges must see the receiver's busy state and the override. A prompt hook
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


# Every judge in hooks/call_judge.py must have a row in the model-per-role table
# (docs/decisions/agent-model-cap.md), and that row's model must equal the module's model.
RECORD = os.path.join(os.path.dirname(SETTINGS), "docs", "decisions", "agent-model-cap.md")
ROW_NAMES = {"Agent": "Agent spawn judge", "AskUserQuestion": "question reviewer"}  # first-cell words of each row


def table_rows(text):
    """Table rows as cell lists."""
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in text.splitlines()
            if line.startswith("|")]


def table_gaps(text, judges):
    """One line per judge the table does not name, or names with another model. judges: tool -> judge tuple."""
    rows = table_rows(text)
    gaps = []
    for tool, judge in judges.items():
        named = [r for r in rows if len(r) >= 2 and ROW_NAMES.get(tool, tool) in r[0]]
        model = judge[1] or ""
        if not named:
            gaps.append("%s: no model-table row names it" % tool)
        elif not any(model and model in r[1] for r in named):
            gaps.append("%s: table model is not %s" % (tool, model))
    return gaps


class JudgeModelRows(unittest.TestCase):
    def setUp(self):
        with open(RECORD, encoding="utf-8") as f:
            self.text = f.read()

    def test_every_call_judge_judge_has_a_row_with_its_model(self):
        judges = call_judge_judges()
        self.assertEqual(sorted(judges), sorted(ROW_NAMES), "call_judge.py judges changed; update ROW_NAMES")
        self.assertEqual(table_gaps(self.text, judges), [])

    def test_the_question_row_names_the_standing_grant(self):
        # The reviewer runs Opus under the owner's class-level standing grant (decision question-reviewer-agent-hook).
        row = [r for r in table_rows(self.text) if len(r) >= 2 and ROW_NAMES["AskUserQuestion"] in r[0]]
        self.assertTrue(row and "standing grant" in row[0][1], "the question reviewer row does not name its standing grant")

    def test_check_goes_red_when_the_agent_row_is_missing(self):
        # Mutation: take the Agent row's name out. The check must name it.
        self.assertTrue(any(ROW_NAMES["Agent"] in r[0] for r in table_rows(self.text)),
                        "the judge row changed; update this mutation")
        mutated = self.text.replace(ROW_NAMES["Agent"], "")
        gaps = table_gaps(mutated, call_judge_judges())
        self.assertTrue(any(g.startswith("Agent:") for g in gaps), gaps)

    def test_check_goes_red_when_the_table_model_differs(self):
        judges = call_judge_judges()
        wrong = dict(judges, Agent=(judges["Agent"][0], "claude-haiku-9-9") + tuple(judges["Agent"][2:]))
        self.assertTrue(any(g.startswith("Agent: table model") for g in table_gaps(self.text, wrong)))


if __name__ == "__main__":
    unittest.main()
