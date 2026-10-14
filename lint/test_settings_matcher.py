#!/usr/bin/env python3
"""The PreToolUse matcher that routes to hooks/guard.py must cover every tool the guard judges.
Run: python3 lint/test_settings_matcher.py. Without Workflow and start_session in the matcher,
the guard's subagent-model-floor never sees those calls.
"""
import json, os, re, unittest

SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings.json")


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


# The decision-record judge: a prompt hook whose prompt holds this rule id.
JUDGE_RULE = "speak-rewrite-superseded-in-place"


def decision_judge(tool):
    """The one PreToolUse prompt hook for `tool` that judges the decision-record rule."""
    hits = [h for e in json.load(open(SETTINGS))["hooks"]["PreToolUse"] if e["matcher"] == tool
            for h in e["hooks"] if h.get("type") == "prompt" and JUDGE_RULE in h.get("prompt", "")]
    if len(hits) != 1:
        raise AssertionError("want one decision judge for %s, found %d" % (tool, len(hits)))
    return hits[0]


def glob_to_regex(glob):
    """Gitignore-style subset: **/ is any depth, trailing /** is everything under, * is one segment."""
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("/**", i) and i + 3 == len(glob):
            out.append("(?:/.*)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class DecisionJudgeMatch(unittest.TestCase):
    # Docs (code.claude.com/docs/en/hooks): "To match a directory named src at any depth,
    # write Edit(**/src/**)". The docs show Edit examples only; the Write form is pinned by intent.
    def test_if_matches_decisions_folder_at_any_depth(self):
        for tool in ("Edit", "Write"):
            with self.subTest(tool=tool):
                cond = decision_judge(tool).get("if", "")
                self.assertTrue(cond.startswith(tool + "(") and cond.endswith(")"), cond)
                rx = glob_to_regex(cond[len(tool) + 1:-1])
                for path in ("decisions/x.md", "docs/decisions/x.md", "a/b/decisions/c/d.md"):
                    self.assertRegex(path, rx)
                for path in ("docs/x.md", "docs/decisionsX/x.md"):
                    self.assertNotRegex(path, rx)

    def test_prompt_does_not_answer_ok_for_paths_outside_decisions(self):
        for tool in ("Edit", "Write"):
            with self.subTest(tool=tool):
                prompt = decision_judge(tool)["prompt"]
                self.assertNotIn("not under a decisions/ folder", prompt)
                self.assertIn(JUDGE_RULE, prompt)

    def test_owner_paths_still_fire_and_lookalike_folders_do_not(self):
        # Green pins, owner ruling 2026-10-13. Commit 8f9a500 widened the glob to any depth.
        for tool in ("Edit", "Write"):
            with self.subTest(tool=tool):
                cond = decision_judge(tool)["if"]
                rx = glob_to_regex(cond[len(tool) + 1:-1])
                for path in ("x/decisions/a.md", "decisions/sub/b.md", "decisions/subagent-model-cap.md"):
                    self.assertRegex(path, rx)
                for path in ("mydecisions/a.md", "decisions-old/a.md"):
                    self.assertNotRegex(path, rx)


# A prompt or agent hook names its model. Since 2026-10-08 the evaluator has rejected the bare
# alias "haiku" (stderr unrecognized_model, query_source hook_prompt), so each judge failed and
# let calls through. A full id starts with "claude-".
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

    def test_sendmessage_prompt_does_not_claim_the_receiver_is_invisible(self):
        for h in pre_tool_hooks("SendMessage"):
            if h.get("type") == "prompt":
                self.assertNotIn("cannot see the receiver", h.get("prompt", ""))


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
        named = "AskUserQuestion, Agent, Edit, Write, SendMessage"
        self.assertIn(named, self.text, "the judge row changed; update this mutation")
        gaps = table_gaps(self.text.replace(named, "AskUserQuestion, Agent, Edit, Write"), list(judge_hooks()))
        self.assertTrue(any(g.startswith("SendMessage:") for g in gaps), gaps)


if __name__ == "__main__":
    unittest.main()
