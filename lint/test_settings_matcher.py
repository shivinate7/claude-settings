#!/usr/bin/env python3
"""The PreToolUse matcher that routes to hooks/guard.py must cover every tool the guard judges.
Run: python3 lint/test_settings_matcher.py. Without Workflow and start_session in the matcher,
the guard's agent-model-floor never sees those calls.
It also pins the page-tool names in settings.json's permissions.allow: cloud page writes must not ask,
and ArtifactComments posts visible text, so it stays asking.
"""
import ast, glob, json, os, re, sys, unittest

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


SHARED_NAMES = os.environ.get("SHARED_NAMES_UNDER_TEST") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "shared_names.py")


def remote_outward_tools():
    """REMOTE_OUTWARD_TOOLS of hooks/shared_names.py, the one home of the claude-code-remote tools an agent may not
    call. SHARED_NAMES_UNDER_TEST points the test at another copy (a red run on a stand-in list)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("shared_names_under_test", SHARED_NAMES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.REMOTE_OUTWARD_TOOLS)


class RemoteOutwardMatcher(unittest.TestCase):
    def test_guard_matcher_covers_every_outward_tool(self):
        # The guard refuses an agent's call to each outward tool, so the guard's matcher must see every one.
        # The list is read from its one home, never copied into this file.
        tools = remote_outward_tools()
        self.assertTrue(tools, "REMOTE_OUTWARD_TOOLS is empty: the matcher has no outward list to check")
        matchers = guard_matchers()
        self.assertTrue(matchers, "no guard.py entry in settings.json PreToolUse")
        for tool in tools:
            with self.subTest(tool=tool):
                self.assertTrue(tool.startswith("mcp__claude-code-remote__"),
                                "%r is not a full claude-code-remote tool name" % tool)
                self.assertTrue(any(re.fullmatch(m, tool) for m in matchers),
                                "no guard matcher covers %s" % tool)


# Every tool a guard judges. The guard.py entry's matcher must match each one, or the guard never sees that call.
HOOKS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
GUARD_SOURCE = os.path.join(HOOKS, "guard.py")
GUARD_MERGE_SOURCE = os.path.join(HOOKS, "guard_merge.py")
# The constants that name the tools each file dispatches on, read by import and never copied here.
# READ_ONLY_TOOLS is left out: guard.py returns at once for Read and Grep ("no rule judges them"), so a matcher
# that skips them is right, and requiring them would be a false alarm. decision_watch's MERGE_TOOLS is left out
# too: no PreToolUse entry runs decision_watch.py, and its mod reads the tool calls from the transcript after a turn.
GUARD_NAMES = ("SPAWN_TOOLS", "START_TOOLS", "SESSION_TOOL", "CREATE_SESSION_TOOL", "SIM_MCP", "PAGE_TOOL",
               "DATA_TOOL", "REMOTE_OUTWARD_TOOLS", "SHELL_TOOLS", "WRITE_TOOLS")
MERGE_NAMES = ("MERGE_TOOLS", "TRUST_TOOLS", "ARCHIVE_TOOL", "BRIEF_TOOL")
# The six GitHub MCP write tools the owner named. Each one must be matched, whether or not a guard judges it yet.
GITHUB_WRITE_TOOLS = tuple("mcp__github__" + short for short in (
    "merge_pull_request", "create_pull_request", "push_files", "create_or_update_file", "delete_file",
    "update_pull_request"))


def load_hook(name, path):
    """Import one hook file by path. hooks/ goes first on sys.path, so its sibling imports resolve."""
    import importlib.util
    if HOOKS not in sys.path:
        sys.path.insert(0, HOOKS)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def flatten(value):
    """A tool-name constant as a list of names: one string, or a tuple of strings and tuples."""
    if isinstance(value, str):
        return [value]
    return [name for part in value for name in flatten(part)]


def literal_names(side):
    """The string constants a comparison side holds: one constant, or the constants of a tuple, list or set of them."""
    if isinstance(side, ast.Constant) and isinstance(side.value, str):
        return [side.value]
    if isinstance(side, (ast.Tuple, ast.List, ast.Set)):
        return [name for elt in side.elts for name in literal_names(elt)]
    return []


def compared_with_tool(source):
    """The string constants compared with `tool` in one source text (==, !=, in, not in). ast parses code only, so a
    name inside a string or a comment is never read as a comparison."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        sides = [node.left] + node.comparators
        if not any(isinstance(side, ast.Name) and side.id == "tool" for side in sides):
            continue
        for side in sides:
            found.update(literal_names(side))
    return found


# Files where `tool` is the PreToolUse tool name, so each string compared with it is a tool name. The other guard_*.py
# files reuse `tool` for a shell word (`pkill` in guard_kill.py, `ps` in guard_argv.py), so only their GitHub names count.
TOOL_NAME_FILES = ("guard.py", "guard_merge.py")


def judged_names_in_guard_files():
    """Every tool name that guard.py or a guard_*.py rule family compares with `tool`."""
    found = set()
    for path in glob.glob(os.path.join(HOOKS, "guard*.py")):
        with open(path, encoding="utf-8") as f:
            names = compared_with_tool(f.read())
        if os.path.basename(path) not in TOOL_NAME_FILES:
            names = {name for name in names if name.startswith("mcp__github__")}
        found |= names
    return found


class JudgedToolMatcher(unittest.TestCase):
    """The guard.py PreToolUse entry's matcher covers every tool the guard family judges."""

    def setUp(self):
        self.matchers = guard_matchers()

    def unmatched(self, tools):
        return [tool for tool in tools if not any(re.fullmatch(m, tool) for m in self.matchers)]

    def judged_tools(self):
        guard = load_hook("guard_judged", GUARD_SOURCE)
        merge = load_hook("guard_merge_judged", GUARD_MERGE_SOURCE)
        names = []
        for module, constants in ((guard, GUARD_NAMES), (merge, MERGE_NAMES)):
            for constant in constants:
                self.assertTrue(hasattr(module, constant),
                                "%s has no %s: a renamed constant hides its tools from this test"
                                % (os.path.basename(module.__file__), constant))
                names += flatten(getattr(module, constant))
        names += list(GITHUB_WRITE_TOOLS) + sorted(judged_names_in_guard_files())
        return sorted(set(names))

    def test_guard_matcher_covers_every_judged_tool(self):
        self.assertTrue(self.matchers, "no guard.py entry in settings.json PreToolUse")
        self.assertTrue(judged_names_in_guard_files(),
                        "the scan found no tool name compared with `tool` in the guard files: the scan is broken")
        missed = self.unmatched(self.judged_tools())
        if missed:
            self.fail("no guard matcher covers: %s" % ", ".join(missed))

    def test_guard_files_scan_leaves_out_shell_words(self):
        # Scope first: the scan reads guard.py's string comparisons at all. Then guard_kill.py's and guard_argv.py's
        # shell words are left out, since their `tool` is no tool name.
        with open(GUARD_SOURCE, encoding="utf-8") as f:
            self.assertTrue(compared_with_tool(f.read()), "guard.py has no string compared with `tool`: nothing is read")
        found = judged_names_in_guard_files()
        for word in ("pkill", "ps", "npm"):
            with self.subTest(word=word):
                self.assertNotIn(word, found, "the scan reads the shell word %r as a tool name" % word)

    def test_guard_matcher_covers_the_six_github_write_tools(self):
        self.assertTrue(self.matchers, "no guard.py entry in settings.json PreToolUse")
        missed = self.unmatched(GITHUB_WRITE_TOOLS)
        if missed:
            self.fail("no guard matcher covers: %s" % ", ".join(missed))

    def test_scan_reads_code_and_not_strings_or_comments(self):
        # Each line is a real comparison, or text that only looks like one: a comment line, a trailing comment, a
        # comment opener (#, /*, //) in a string, a multi-line string, a lone quote in text, and a comparison with
        # another name.
        sample = "\n".join([
            'if tool == "mcp__github__planted_eq": pass',
            'if tool in ("mcp__github__planted_in_a",',
            '            "mcp__github__planted_in_b"): pass',
            'if name == "mcp__github__not_a_tool": pass',
            'TEXT = "# tool == \'mcp__github__hash_in_string\'"',
            'NOTE = """',
            'if tool == "mcp__github__in_a_string": pass',
            'if tool == "Edit": pass',
            '"""',
            'WORDS = "don\'t"',
            'OPEN, FOUND = "/*", tool == "mcp__github__after_block_opener"',
            'URL, FOUND2 = "http://x", tool == "mcp__github__after_double_slash"',
            '# if tool == "mcp__github__in_a_comment": pass',
            '# if tool == "Bash": pass',
            'FLAG = tool == "mcp__github__before_trailing_comment"  # tool == "mcp__github__in_trailing_comment"',
            'if tool == "mcp__github__after_lone_quote": pass',
            'if tool not in ("Skill", "ExitWorktree"): pass',
            'if tool != "Write": pass',
        ])
        self.assertEqual(compared_with_tool(sample), {
            "mcp__github__planted_eq", "mcp__github__planted_in_a", "mcp__github__planted_in_b",
            "mcp__github__after_block_opener", "mcp__github__after_double_slash",
            "mcp__github__before_trailing_comment", "mcp__github__after_lone_quote",
            "Skill", "ExitWorktree", "Write"})

    def test_scan_of_empty_source_finds_nothing(self):
        self.assertEqual(compared_with_tool(""), set())


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

    def test_guard_matcher_covers_artifact(self):
        # Rule page-stale refuses a waiting-page publish made by the Artifact tool, so the guard must see that call.
        matchers = guard_matchers()
        self.assertTrue(any(re.fullmatch(m, "Artifact") for m in matchers),
                        "no guard matcher covers Artifact: %r" % matchers)

    def test_guard_matcher_covers_artifact_comments(self):
        # Rule page-thread-reply refuses a reply into a comment thread on the waiting page, made by the
        # ArtifactComments tool, so the guard must see that call. Matchers are whole-name regexes, so
        # Artifact and ArtifactData do not reach it.
        matchers = guard_matchers()
        self.assertTrue(any(re.fullmatch(m, "ArtifactComments") for m in matchers),
                        "no guard matcher covers ArtifactComments: %r" % matchers)

    def test_guard_matcher_covers_trust_card_tools(self):
        # Rule trust-card-in-build refuses these two calls in a cs-build session, so the first guard.py
        # matcher must fire on both full tool names.
        matcher = guard_matchers()[0]
        for tool in ("mcp__claude-code-remote__confirm_repository_trust",
                     "mcp__claude-code-remote__request_computer_folder"):
            with self.subTest(tool=tool):
                self.assertTrue(re.fullmatch(matcher, tool), "the first guard matcher does not cover %s: %r" % (tool, matcher))

    def test_guard_matcher_covers_send_message(self):
        # Rule lane-one-topic refuses a brief sent to a lane of another topic, so a guard matcher must see send_message.
        matchers = guard_matchers()
        tool = "mcp__claude-code-remote__send_message"
        self.assertTrue(any(re.fullmatch(m, tool) for m in matchers),
                        "no guard matcher covers %s: %r" % (tool, matchers))

    def test_guard_matcher_covers_mcp_update_pull_request(self):
        # Rule records-page-ready refuses marking a pull request ready by MCP update_pull_request draft:false, so a guard matcher must see that call.
        matchers = guard_matchers()
        tool = "mcp__github__update_pull_request"
        self.assertTrue(any(re.fullmatch(m, tool) for m in matchers),
                        "no guard matcher covers %s: %r" % (tool, matchers))

    def test_guard_matcher_covers_sendmessage(self):
        # Rule sendmessage-session-id refuses a SendMessage that names a cloud session, so a guard matcher must see it.
        matchers = guard_matchers()
        self.assertTrue(matchers)
        tool = "SendMessage"
        self.assertTrue(any(re.fullmatch(m, tool) for m in matchers),
                        "no guard matcher covers %s: %r" % (tool, matchers))

    def test_session_start_hook_matcher_covers_compact(self):
        # After a compaction the start hook must run, so the session learns its hooks lag main.
        with open(SETTINGS, encoding="utf-8") as f:
            entries = json.load(f)["hooks"]["SessionStart"]
        starts = [e for e in entries if any("/hooks/session_start.sh" in h.get("command", "") for h in e.get("hooks", []))]
        self.assertEqual(len(starts), 1, "want one SessionStart entry running session_start.sh, found %d" % len(starts))
        matcher = starts[0].get("matcher", "")
        for source in ("startup", "resume", "compact"):
            with self.subTest(source=source):
                self.assertTrue(covers(starts[0], source),
                                "the session_start.sh SessionStart matcher %r does not cover %s" % (matcher, source))

    def test_cloud_pull_session_start_entry_does_not_match_compact(self):
        # A compaction mid-task must not run the cloud pull: it would move main and reinstall the pin under the session.
        # The entry is found by its pin install, merge/install_from_main.sh, which only the cloud pull runs.
        with open(SETTINGS, encoding="utf-8") as f:
            entries = json.load(f)["hooks"]["SessionStart"]
        pulls = [e for e in entries if any("merge/install_from_main.sh" in h.get("command", "") for h in e.get("hooks", []))]
        self.assertEqual(len(pulls), 1, "want one SessionStart entry running merge/install_from_main.sh, found %d" % len(pulls))
        matcher = pulls[0].get("matcher", "")
        self.assertFalse(covers(pulls[0], "compact"), "the cloud-pull SessionStart matcher %r covers compact" % matcher)
        self.assertTrue(covers(pulls[0], "startup"), "the cloud-pull SessionStart matcher %r does not cover startup" % matcher)
        self.assertTrue(covers(pulls[0], "resume"), "the cloud-pull SessionStart matcher %r does not cover resume" % matcher)


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
# hooks/question_outcome.py. A failed or timed-out model call lets the question through. Code reads the
# form lines and the marks on each option (hooks/question_form.py), so the prompt text is the only home of
# the items code cannot decide, and these cases pin that text.
# An agent hook takes only these keys (probed on Claude Code 2.1.296 on Windows). The prompt
# hooks beside it carry `continueOnBlock`, which is not one of them.
COMMAND_HOOK_KEYS = {"type", "command", "if", "timeout", "statusMessage", "once", "async"}
OPUS_PREFIX = "claude-opus-"
# Each rubric item the prompt must name, with the patterns that must all match the prompt. The prompt is
# whitespace-folded and matched without case. Code reads that the Goal, Problem and Based on lines are there
# (question_form.chat_hit); the prompt judges how they read, and never names a line.
RUBRIC = {
    "goal in the owner's terms": [r"\bgoal\b.{0,40}\bowner.s terms\b"],
    "problem is one plain sentence": [r"\bproblem\b.{0,60}\bplain\b.{0,60}\bneeds? his word\b"],
    "premises in plain words": [r"\bpremises?\b.{0,40}\bplain words\b"],
    "gain and lose are plain": [r"\bgains?\b.{0,80}\bplain\b|\bplain\b.{0,80}\bgains?\b", r"\blos(?:e|es|ing|s)\b"],
    "no unexplained ids": [r"\bunexplained\b.{0,40}\b(?:ids?|names?|identifiers?)\b"
                           r"|\b(?:ids?|identifiers?)\b.{0,80}\b(?:(?:un)?explain\w*|(?:un)?gloss\w*|plain)\b"],
    "nothing outside the box": [r"\boutside\b.{0,20}\bbox\b"],
    "one option recommended": [r"\bone\b.{0,40}\brecommend|\brecommend\w*\b.{0,40}\bone\b"],
}
# One sentence per item: a prompt that meets the rubric, and the mutants the check must see.
SAMPLE = {
    "goal in the owner's terms": "The Goal is in the owner's terms.",
    "problem is one plain sentence": "The Problem is one plain sentence that says why it needs his word.",
    "premises in plain words": "Each premise is in plain words.",
    "gain and lose are plain": "Each option's gain and lose are plain effects on the owner.",
    "no unexplained ids": "Reject unexplained ids.",
    "nothing outside the box": "Nothing points outside the box.",
    "one option recommended": "One option is recommended.",
}


def rubric_gaps(prompt):
    """The rubric items the prompt does not name, in RUBRIC order."""
    text = " ".join(prompt.split())
    return [item for item, pats in RUBRIC.items() if not all(re.search(p, text, re.I) for p in pats)]


# The premise kinds have two readers and no copy: the table in docs/decisions/premise-format.md says what each
# means, and PREMISE_KINDS in hooks/precompact_handoff.py is the list the form check reads. The question
# reviewer prompt lists none. PREMISE_FORMAT_UNDER_TEST points the test at another copy of the table, as SETTINGS_UNDER_TEST does.
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

    def test_the_waiting_page_write_runs_the_call_judge_hook(self):
        # Ruled Nov 1 11:51 CST: a waiting-page item write gets the same model review as a chat question,
        # so the one command hook that runs call_judge.py also runs on ArtifactData. Its matcher keeps the two
        # chat tools, so one override path lifts a refusal on any of the three.
        rows = call_judge_entries()
        self.assertEqual(len(rows), 1, "want one call_judge.py command hook, found %d" % len(rows))
        entry = rows[0][0]
        self.assertTrue(covers(entry, "ArtifactData"),
                        "call_judge.py does not run on ArtifactData: matcher %r" % entry.get("matcher"))
        self.assertTrue(covers(entry, "Agent") and covers(entry, "AskUserQuestion"),
                        "call_judge.py lost a chat tool: matcher %r" % entry.get("matcher"))

    def test_no_prompt_or_agent_hook_on_the_waiting_page_write(self):
        bad = [h.get("type") for e in pre_tool_entries() if covers(e, "ArtifactData") for h in e["hooks"]
               if h.get("type") in JUDGE_TYPES]
        self.assertEqual(bad, [], "a prompt or agent hook runs on ArtifactData: %s" % bad)

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
        # It tests the check itself, not settings.json, so an edit to settings.json cannot change its result.
        self.assertEqual(set(SAMPLE), set(RUBRIC), "SAMPLE and RUBRIC name different items")
        self.assertEqual(rubric_gaps(" ".join(SAMPLE.values())), [])
        self.assertEqual(rubric_gaps(""), list(RUBRIC))
        for item in RUBRIC:
            with self.subTest(dropped=item):
                rest = " ".join(v for k, v in SAMPLE.items() if k != item)
                self.assertEqual(rubric_gaps(rest), [item])

    def test_the_premise_table_kinds_equal_the_kinds_the_form_check_reads(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
        import question_form
        from precompact_handoff import PREMISE_KINDS
        with open(PREMISE_FORMAT, encoding="utf-8") as f:
            table = table_kinds(f.read())
        self.assertTrue(table, "no kind rows in %s" % PREMISE_FORMAT)
        self.assertEqual(sorted(table), sorted(question_form.PREMISE_KINDS),
                         "premise table kinds %s, question_form kinds %s: update the one that drifted"
                         % (table, list(question_form.PREMISE_KINDS)))
        self.assertIs(question_form.PREMISE_KINDS, PREMISE_KINDS,
                      "question_form must import PREMISE_KINDS from precompact_handoff, never copy it")

    def test_the_reviewer_prompt_lists_no_premise_kinds(self):
        # The form check is the one reader of the kinds; a list in the prompt would be a second copy.
        listed = prompt_kinds(self.question_prompt())
        self.assertEqual(listed, [], "the question reviewer prompt lists source kinds %s: code reads them" % listed)

    def test_the_kinds_readers_see_a_kind_added_or_dropped(self):
        # It tests the two readers, not settings.json, so an edit to settings.json cannot change its result.
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

    def test_retired_stubs_are_gone(self):
        # lint/check_hook_stubs.py allowed their removal once no settings.json from the last 14 days called them.
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        for rel in ("hooks/question_outcome.py", "lint/ste_gate.py", "lint/md_sweep.py"):
            with self.subTest(script=rel):
                self.assertFalse(os.path.exists(os.path.join(root, rel)), "%s is back" % rel)


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
ROW_NAMES = {"Agent": "Agent spawn judge", "AskUserQuestion": "question reviewer",
             "ArtifactData": "question reviewer"}  # first-cell words of each row; the question reviewer row covers both


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


class PermissionsAllow(unittest.TestCase):
    """permissions.allow in settings.json holds the page-tool names that cloud page writes need, so the writes do
    not ask. ArtifactComments posts visible text, so it stays off the list. Each name is a literal here. The list
    itself is read from SETTINGS, never copied."""

    def allow_list(self):
        # Scope first: a moved key or an empty list must fail here, or the absence case would pass on nothing.
        with open(SETTINGS, encoding="utf-8") as handle:
            permissions = json.load(handle).get("permissions")
        self.assertIsInstance(permissions, dict, "settings.json has no permissions object")
        allow = permissions.get("allow")
        self.assertIsInstance(allow, list, "settings.json permissions.allow is not a list")
        self.assertTrue(allow, "settings.json permissions.allow is empty")
        return allow

    def test_artifactdata_is_allowed(self):
        self.assertIn("ArtifactData", self.allow_list(),
                      "ArtifactData is missing from permissions.allow, so cloud page writes would ask")

    def test_db_usage_is_allowed(self):
        self.assertIn("mcp__claude-artifacts__db_usage", self.allow_list(),
                      "db_usage is missing from permissions.allow, so its page write would ask")

    def test_read_artifact_is_allowed(self):
        self.assertIn("mcp__claude-artifacts__read_artifact", self.allow_list(),
                      "read_artifact is missing from permissions.allow, so its page write would ask")

    def test_artifactcomments_is_not_allowed(self):
        # ArtifactComments posts visible text, so it stays asking. A scoped form such as ArtifactComments(...)
        # allows it too, so that form is held as well.
        held = [entry for entry in self.allow_list()
                if entry == "ArtifactComments" or entry.startswith("ArtifactComments(")]
        self.assertFalse(held, "ArtifactComments is on permissions.allow, but it posts visible text and must stay asking")


class CoordinatorAutoMergeMatcher(unittest.TestCase):
    def test_first_guard_matcher_names_enable_pr_auto_merge(self):
        # Rule coordinator-scope (decision session-tiers): arming auto-merge is a merge, so the first guard matcher
        # must name it, or the guard never judges a coordinator's arming call. The tool name is typed here as data.
        matchers = guard_matchers()
        self.assertTrue(matchers, "no guard matcher in settings.json")
        tool = "mcp__github__enable_pr_auto_merge"
        self.assertTrue(re.fullmatch(matchers[0], tool),
                        "%s is not in the first guard matcher, so a coordinator's arming call is never judged" % tool)


if __name__ == "__main__":
    unittest.main()
