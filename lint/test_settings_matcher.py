#!/usr/bin/env python3
"""The PreToolUse matcher that routes to hooks/guard.py must cover every tool the guard judges.
Run: python3 lint/test_settings_matcher.py. Without Workflow and start_session in the matcher,
the guard's subagent-model-floor never sees those calls.
"""
import json, os, re, sys, unittest

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

    def test_prose_judge_command_hooks_cover_edit_and_write(self):
        # One handler per tool is allowed: each carries its own `if` (see IfFilters).
        rows = [(e, h) for e in pre_tool_entries() for h in e["hooks"]
                if h.get("type") == "command" and "prose_judge.py" in script_names(h.get("command", ""))]
        self.assertTrue(rows, "no prose_judge.py command hook")
        for tool in ("Edit", "Write"):
            self.assertTrue(any(covers(e, tool) for e, _h in rows), "prose_judge.py does not run on %s" % tool)
        for entry, hook in rows:
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


# `if` filters: a handler whose `if` rule does not match the tool call starts no shell.
# Documented (docs hooks "Common fields", docs permissions "Read and Edit"): one permission rule per
# handler; tool events only, and a handler with `if` on any other event never runs; gitignore
# patterns; `path` is relative to the current directory and matches only files under it; `//path` is
# absolute; `/path` anchors at the settings source, which is `~/.claude` because this file installs as
# user settings; Windows paths become POSIX (`C:\x` is `/c/x`) before matching.
# Not documented, so modeled the safe way: the rule's tool name must equal the call's tool name (no
# doc says Edit(...) also covers Write), and matching is case sensitive. Each is one line below.
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied")
FILE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
RULE = re.compile(r"(\w+)\((.+)\)\Z", re.S)
CWD = "C:\\Users\\dev\\proj"
CONFIG_DIR = "/c/Users/dev/.claude"


def posix(path):
    p = path.replace("\\", "/")
    return "/%s%s" % (p[0].lower(), p[2:]) if re.match(r"[A-Za-z]:(/|\Z)", p) else p


def glob_re(pat):
    """gitignore glob: `*` stays inside one segment, `**/` spans zero or more directories."""
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("/**", i) and i + 3 == len(pat):
            out, i = out + "/.*", i + 3
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile(out + r"\Z")


def if_matches(rule, tool, path, cwd=CWD):
    m = RULE.match(rule)
    if not m or m.group(1) not in FILE_TOOLS:
        raise ValueError("this matcher models file-tool rules only: %r" % rule)
    name, pat = m.groups()
    if name != tool or path is None:  # strict tool name: the one place to change if the docs say otherwise
        return False
    if pat.startswith("~"):
        raise ValueError("this matcher does not model %r" % rule)
    p = posix(path)
    if pat.startswith("//"):
        base, pat = "/", pat[2:]
    elif pat.startswith("/"):
        base, pat = CONFIG_DIR + "/", pat[1:]
    else:
        base, pat = posix(cwd).rstrip("/") + "/", pat[2:] if pat.startswith("./") else pat
    if not p.startswith(base):
        return False
    if "/" not in pat.rstrip("/"):  # a bare name matches at any depth under the anchor
        pat = "**/" + pat
    return glob_re(pat).match(p[len(base):]) is not None


def group_covers(entry, tool):
    matcher = entry.get("matcher", "")
    return matcher in ("", "*") or re.fullmatch(matcher, tool) is not None


def handlers(event, script=None):
    """(entry, hook) for each command handler under an event, filtered to one script when given."""
    with open(SETTINGS, encoding="utf-8") as f:
        entries = json.load(f)["hooks"].get(event, [])
    return [(e, h) for e in entries for h in e["hooks"] if h.get("type") == "command"
            and (script is None or script in script_names(h.get("command", "")))]


def fires(event, tool, path=None):
    """The scripts, sorted, of every handler that starts a shell for this tool call."""
    return sorted(n for e, h in handlers(event) if group_covers(e, tool)
                  and ("if" not in h or if_matches(h["if"], tool, path))
                  for n in script_names(h["command"]))


def proj(*parts):
    return "\\".join((CWD,) + parts)


def core(pattern):
    """A pattern without its anchor spelling: `*.md`, `**/*.md` and `//**/*.md` share one core."""
    return re.sub(r"^(?://)?(?:\*\*/)?", "", pattern)


def rule_pairs(event, script):
    return sorted((RULE.match(h["if"]).group(1), core(RULE.match(h["if"]).group(2)))
                  for _e, h in handlers(event, script) if "if" in h)


class IfMatcherModel(unittest.TestCase):
    """The matcher above follows the docs; these cases pin what it assumes."""

    def test_bare_name_matches_at_any_depth_under_cwd_only(self):
        self.assertTrue(if_matches("Edit(*.md)", "Edit", proj("a.md")))
        self.assertTrue(if_matches("Edit(*.md)", "Edit", proj("docs", "a.md")))
        self.assertFalse(if_matches("Edit(*.md)", "Edit", "C:\\Users\\dev\\other\\a.md"))
        self.assertFalse(if_matches("Edit(*.md)", "Edit", proj("a.mdx")))

    def test_double_slash_is_absolute_so_it_reaches_outside_cwd(self):
        self.assertTrue(if_matches("Edit(//**/*.md)", "Edit", "C:\\Users\\dev\\other\\a.md"))
        self.assertTrue(if_matches("Edit(//**/*.md)", "Edit", proj("a.md")))

    def test_decisions_pattern_needs_a_decisions_segment(self):
        self.assertTrue(if_matches("Edit(**/decisions/**)", "Edit", proj("decisions", "x.md")))
        self.assertTrue(if_matches("Edit(**/decisions/**)", "Edit", proj("docs", "decisions", "x.md")))
        self.assertFalse(if_matches("Edit(**/decisions/**)", "Edit", proj("decisions.md")))
        self.assertFalse(if_matches("Edit(**/decisions/**)", "Edit", proj("Decisions", "x.md")))

    def test_a_path_with_a_slash_is_anchored_at_cwd(self):
        self.assertTrue(if_matches("Edit(.claude/settings.json)", "Edit", proj(".claude", "settings.json")))
        self.assertFalse(if_matches("Edit(.claude/settings.json)", "Edit", proj("sub", ".claude", "settings.json")))

    def test_leading_slash_anchors_at_the_config_dir_not_the_project(self):
        self.assertFalse(if_matches("Edit(/.claude/settings.json)", "Edit", proj(".claude", "settings.json")))
        self.assertTrue(if_matches("Edit(/.claude/settings.json)", "Edit", "C:\\Users\\dev\\.claude\\.claude\\settings.json"))

    def test_the_rule_tool_name_must_equal_the_call_tool_name(self):
        self.assertFalse(if_matches("Edit(*.md)", "Write", proj("a.md")))
        self.assertFalse(if_matches("Edit(*.md)", "MultiEdit", proj("a.md")))


STE_TOOLS = ("Write", "Edit", "MultiEdit")  # lint/ste_gate.py main(): tool not in (Write, Edit, MultiEdit) returns


class IfFilters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        here = os.path.dirname(os.path.abspath(__file__))
        for d in (here, os.path.join(here, "..", "hooks")):
            if d not in sys.path:
                sys.path.insert(0, d)
        import shared_names, ste_gate, ste_lint
        cls.watched = [n.lstrip("/") for n in shared_names.PROJECT_FROZEN_FILES]
        cls.ste_suffixes = sorted(set(ste_gate.MD_SUFFIXES) | set(ste_lint.UI_SUFFIXES))
        cls.ui_suffixes = sorted(ste_lint.UI_SUFFIXES)

    def test_a_ts_edit_reaches_only_the_guard(self):
        for tool in FILE_TOOLS:
            for name in ("src\\app.ts", "data.json", "hooks\\x.py", "notes.txt"):
                with self.subTest(tool=tool, name=name):
                    self.assertEqual(fires("PreToolUse", tool, proj(name)), ["guard.py"])

    def test_decision_records_keep_prose_judge_and_ste_gate(self):
        both = ["guard.py", "prose_judge.py", "ste_gate.py"]
        for name in ("decisions\\x.md", "docs\\decisions\\x.md"):
            for tool, want in (("Edit", both), ("Write", both), ("MultiEdit", ["guard.py", "ste_gate.py"])):
                with self.subTest(tool=tool, name=name):
                    self.assertEqual(fires("PreToolUse", tool, proj(name)), want)
        for tool in ("Edit", "Write"):
            with self.subTest(tool=tool, name="decisions\\x.json"):
                self.assertEqual(fires("PreToolUse", tool, proj("decisions", "x.json")), ["guard.py", "prose_judge.py"])

    def test_markdown_and_ui_files_outside_decisions_reach_ste_gate_only(self):
        names = ["README.md", "docs\\a.markdown"] + ["src\\App" + s for s in self.ui_suffixes]
        for tool in STE_TOOLS:
            for name in names:
                with self.subTest(tool=tool, name=name):
                    self.assertEqual(fires("PreToolUse", tool, proj(name)), ["guard.py", "ste_gate.py"])

    def test_prose_judge_has_one_handler_each_for_edit_and_write_on_decisions(self):
        self.assertEqual(rule_pairs("PreToolUse", "prose_judge.py"),
                         [("Edit", "decisions/**"), ("Write", "decisions/**")])
        self.assertTrue(all("if" in h for _e, h in handlers("PreToolUse", "prose_judge.py")))

    def test_ste_gate_patterns_equal_the_markdown_and_ui_constants(self):
        every = handlers("PreToolUse", "ste_gate.py")
        self.assertTrue(every, "no ste_gate.py handler")
        self.assertEqual([h["command"][:40] for _e, h in every if "if" not in h], [], "an unfiltered ste_gate handler runs on every file")
        pairs = rule_pairs("PreToolUse", "ste_gate.py")
        want = sorted("*" + s for s in self.ste_suffixes)
        self.assertEqual(sorted({p for _t, p in pairs}), want)
        self.assertEqual(pairs, sorted((t, "*" + s) for t in STE_TOOLS for s in self.ste_suffixes),
                         "each pattern needs a handler for each of Write, Edit and MultiEdit, no repeat")

    def test_config_watch_file_tool_handlers_equal_the_watched_files(self):
        got = sorted(h["if"] for _e, h in handlers("PostToolUse", "config_watch.py") if "if" in h)
        want = sorted("%s(%s)" % (t, n) for t in FILE_TOOLS for n in self.watched)
        self.assertEqual(got, want)

    def test_config_watch_runs_after_a_file_tool_only_on_a_watched_file(self):
        for tool in FILE_TOOLS:
            for name in self.watched:
                with self.subTest(tool=tool, name=name):
                    self.assertIn("config_watch.py", fires("PostToolUse", tool, proj(*name.split("/"))))
            for name in ("src\\app.ts", ".claude\\agents\\x.md"):
                with self.subTest(tool=tool, name=name):
                    self.assertNotIn("config_watch.py", fires("PostToolUse", tool, proj(name)))

    def test_config_watch_shell_and_stop_runs_stay_unfiltered(self):
        for tool in ("Bash", "PowerShell"):
            with self.subTest(tool=tool):
                self.assertIn("config_watch.py", fires("PostToolUse", tool))
        for entry, hook in handlers("PostToolUse", "config_watch.py"):
            if "if" not in hook:
                self.assertEqual([t for t in FILE_TOOLS if group_covers(entry, t)], [],
                                 "an unfiltered config_watch handler runs on every file tool call")
        stop = handlers("Stop", "config_watch.py")
        self.assertTrue(stop, "no Stop handler runs config_watch.py")
        self.assertEqual([h for _e, h in stop if "if" in h], [])

    def test_only_tool_events_carry_if(self):
        with open(SETTINGS, encoding="utf-8") as f:
            events = json.load(f)["hooks"]
        bad = [ev for ev, entries in events.items() if ev not in TOOL_EVENTS
               for e in entries for h in e["hooks"] if "if" in h]
        self.assertEqual(bad, [], "a handler with `if` on a non-tool event never runs")

    def test_no_if_pattern_leads_with_one_slash(self):
        with open(SETTINGS, encoding="utf-8") as f:
            events = json.load(f)["hooks"]
        bad = [h["if"] for entries in events.values() for e in entries for h in e["hooks"]
               if re.match(r"\w+\(/(?!/)", h.get("if", ""))]
        self.assertEqual(bad, [], "in user settings a single leading slash anchors at ~/.claude, not the project")


if __name__ == "__main__":
    unittest.main()
