#!/usr/bin/env python3
"""Cases for lint/hook_catalog.py: the generated page of hooks, prompt judges, mods and skills.

Run: python3 lint/test_hook_catalog.py -v

Owner ask (2026-10-13, 22:25 CDT): one readable page that says, for each hook, judge and mod,
what it does and which model and effort it runs on. The page is generated, never kept by hand.
Owner add (22:26 CDT): skills are in scope too. Their source is the frontmatter description.

Interface the generator must meet. The builder builds to this.
- lint/hook_catalog.py, stdlib only, Python 3.11. Root: the repo root, or env HOOK_CATALOG_ROOT
  (same layout). Every fixture case sets HOOK_CATALOG_ROOT to a temp tree.
- No argument: write docs/catalog.md. `--print`: write the render to stdout, exit 1 while a problem
  stands (the problems go to stderr), else exit 0. stdout is UTF-8 whatever the console codepage.
- `--check`: exit 0 and print nothing when docs/catalog.md equals the render (CRLF normalized).
  Exit 1: one line per problem, naming the offender (stale page, empty source, missing row).
  Exit 2: the path of an input it cannot read (settings.json, the model table, a file it names).
- Sources, read from the root:
  - settings.json `hooks`: one row per registration (event, matcher, `if`, command or prompt).
  - A command names its script as `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/<path>`. Source: a .py
    docstring (ast.get_docstring), or a .sh leading comment block after an optional shebang, which
    stops at the first other line. No docstring is a problem.
  - A command that names no script is inline. Its text is the one-line value in
    lint/hook_catalog_inline.json under its sidecar key: its label (the event, then ` matcher=<m>` and
    ` if=<c>` when present), then ` #` and the first 8 hex digits of the SHA-256 of the command text
    (ruling: a changed command changes its key, so it fails --check until its summary is keyed).
    Its row key is `inline: <label>`. A key with no value, an empty or multi-line value, a key
    written twice, or a sidecar key that matches no inline command is a problem. A missing sidecar is a problem
    too: exit 1, never exit 2.
  - A prompt's first sentence: text up to and including the first ". ", or up to the first
    newline, whichever comes first. An empty first sentence is a problem.
  - Enabled mods: `enabledPlugins` keys `<name>@claude-settings` set true. Source: the text
    under the first heading of mods/<name>/README.md, up to the next heading. No README, or
    empty text, is a problem.
  - Skills: skills/<name>/SKILL.md, frontmatter `description` (plain, quoted, or `>` folded).
    Missing or empty is a problem.
  - Model and effort: the model-table row whose first cell names the script in backticks. None:
    "no model" and "n/a". A prompt hook takes its own `model` field, effort "n/a". A skill takes
    "no model". A script that calls or defines invoke_model (ast) needs its own table row.
    An inline command takes "no model" and "n/a".
- Page: docs/catalog.md. Header row, exactly:
  | Key | Kind | Event | Matcher | If | Model | Effort | What it does |
  Kind: hook, judge, mod or skill. Key: the script path (hook), the first sentence (judge),
  mods/<name> (mod), skills/<name> (skill). A pipe inside a cell is written \\|.
  Event, Matcher and If are "-" when absent. Mods and skills have no event, matcher or if.

Red on main: the generator and the page do not exist. Real-repo cases R1-R9 read this repo.
Fixture cases F1-F29 run the generator on temp trees, so a generator that is silent for every
input fails them. F25-F29 are round 2: F25 and F28 pin the Modes and duplicate-key checks, F26 and F27 pin
the hash-keyed sidecar ruling, and F29 pins the orphan check.
Unit cases U1-U4 pin the table and sentence helpers used here.

Scanner rule: Python docstrings go through ast. The .sh header reader and the frontmatter reader
are hand scanners; they get the comment-opener, lone-quote and multi-line-string cases (F2-F6,
F11-F16). JavaScript is not scanned, so the multi-line template-literal case does not apply.
"""
import ast
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GEN = os.path.join(HERE, "hook_catalog.py")
INLINE_JSON = os.path.join(HERE, "hook_catalog_inline.json")
PAGE = os.path.join(ROOT, "docs", "catalog.md")
TABLE = os.path.join(ROOT, "decisions", "subagent-model-cap.md")
COLUMNS = ["Key", "Kind", "Event", "Matcher", "If", "Model", "Effort", "What it does"]
CMD_PATH = re.compile(r"\$\{CLAUDE_CONFIG_DIR:-\$HOME/\.claude\}/([\w./-]+\.(?:py|sh|mjs|js))")
TABLE_PATH = re.compile(r"`([\w./-]+\.(?:py|sh|mjs|js))`")
LABEL = re.compile(r"^(\S+)(?: matcher=(\S+))?(?: if=(.+))?$")

sys.path.insert(0, HERE)
from test_settings_matcher import SETTINGS, judge_hooks  # noqa: E402  one home for settings.json and the judge walk
from check_skill_model_rows import skill_names  # noqa: E402  one home for "a skill is a folder with SKILL.md"


def read(path, encoding="utf-8-sig"):
    with open(path, encoding=encoding) as handle:
        return handle.read()


def registrations():
    """(event, matcher, if, hook) for each settings.json hook. An absent matcher or if is '-'."""
    for event, entries in json.loads(read(SETTINGS))["hooks"].items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                yield event, entry.get("matcher", "-"), hook.get("if", "-"), hook


def command_script(hook):
    found = CMD_PATH.search(hook.get("command", ""))
    return found.group(1) if found else None


def inline_label(event, matcher, cond):
    """The label of an inline command: its row is "inline: <label>", and its sidecar key adds the hash (sidecar_key)."""
    return event + ("" if matcher == "-" else " matcher=" + matcher) + ("" if cond == "-" else " if=" + cond)


def sidecar_key(label, command):
    """The sidecar key of an inline command, per the ruling: its label, " #", then the first 8 hex digits
    of the SHA-256 of its command text. Written here from the ruling, not imported from the generator."""
    return "%s #%s" % (label, hashlib.sha256(command.encode("utf-8")).hexdigest()[:8])


def first_sentence(prompt):
    """Text up to and including the first '. ', or up to the first newline, whichever is first."""
    text = prompt.strip()
    cuts = [i for i in (text.find("\n"), text.find(". ")) if i != -1]
    end = min(cuts) if cuts else len(text)
    if end < len(text) and text[end] == ".":
        end += 1
    return text[:end].strip()


def split_cells(line):
    """Cells of one markdown table line. An escaped pipe (\\|) stays inside its cell."""
    text = line.strip()
    body = text[1:-1] if text.endswith("|") else text[1:]
    return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", body)]


def page_rows(text):
    """Data rows of every table whose header is COLUMNS, each a dict keyed by column name."""
    rows, state = [], None
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.lstrip().startswith("|"):
            state = None
            continue
        cells = split_cells(line)
        if state is None:
            if cells == COLUMNS:
                state = "separator"
            continue
        if state == "separator":
            state = "body"
            continue
        rows.append(dict(zip(COLUMNS, cells + [""] * len(COLUMNS))))
    return rows


def table_rows():
    """{script path: (model token, effort token)} for each model-table row that names a script."""
    found = {}
    for line in read(TABLE).replace("\r\n", "\n").split("\n"):
        if not line.lstrip().startswith("|"):
            continue
        cells = split_cells(line)
        path = TABLE_PATH.search(cells[0]) if cells else None
        if not path or len(cells) < 3:
            continue
        model = re.match(r"[\w.-]+", cells[1])
        found[path.group(1)] = (model.group(0) if model else "", cells[2].strip("` "))
    return found


def invoke_model_callers():
    """Registered Python scripts that call or define invoke_model. Found with ast."""
    found = set()
    for _event, _matcher, _cond, hook in registrations():
        path = command_script(hook) if hook.get("type") == "command" else None
        if not path or not path.endswith(".py"):
            continue
        for node in ast.walk(ast.parse(read(os.path.join(ROOT, path)))):
            if isinstance(node, ast.FunctionDef) and node.name == "invoke_model":
                found.add(path)
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name == "invoke_model":
                    found.add(path)
    return found


def model_matches(cell, want):
    """The Model cell is the model, optionally followed by a clause: 'haiku' or 'haiku, through ...'."""
    return cell == want or re.match(re.escape(want) + r"[ ,(]", cell) is not None


def generator(root, *args):
    """Run lint/hook_catalog.py on root (None: the real repo). Returns (code, stdout, stderr)."""
    if not os.path.exists(GEN):
        raise AssertionError("lint/hook_catalog.py does not exist yet: the builder writes it")
    env = dict(os.environ)
    env.pop("HOOK_CATALOG_ROOT", None)
    if root is not None:
        env["HOOK_CATALOG_ROOT"] = root
    proc = subprocess.run([sys.executable, GEN, *args], cwd=root or ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


MAIN_SESSION_REFRESH = (
    '[ -n "$CLAUDE_CODE_REMOTE" ] && exit 0; d=$(sed -n "s|^@\\(.*\\)/CLAUDE\\.md$|\\1|p" "${CLAUDE_CONFIG_DI'
    'R:-$HOME/.claude}/CLAUDE.md" | head -n1); case "$d" in "~"/*) d="$HOME${d#\\~}";; esac; [ -n "$d" ] &'
    '& [ -d "$d/.git" ] && git -C "$d" pull -q --ff-only >/dev/null 2>&1; [ -f "$d/install.sh" ] && comma'
    'nd -v bash >/dev/null 2>&1 && bash "$d/install.sh" >/dev/null 2>&1; exit 0'
)


# ---- real repo -------------------------------------------------------------------------------


class RealRepo(unittest.TestCase):
    def page(self):
        if not os.path.exists(PAGE):
            self.fail("docs/catalog.md does not exist yet: the generator writes it")
        return read(PAGE)

    def test_r1_every_script_command_names_a_script_with_a_docstring(self):
        # An inline command names no script. R1b checks its summary instead.
        problems = []
        for event, matcher, _cond, hook in registrations():
            if hook.get("type") != "command":
                continue
            where = "%s matcher=%s" % (event, matcher)
            path = command_script(hook)
            if path is None:
                continue
            if not os.path.isfile(os.path.join(ROOT, path)):
                problems.append("%s: %s does not exist" % (where, path))
            elif path.endswith(".py") and not (ast.get_docstring(ast.parse(read(os.path.join(ROOT, path)))) or "").strip():
                problems.append("%s: %s has no docstring" % (where, path))
        self.assertFalse(problems, "\n".join(problems))

    def test_r1b_every_inline_command_has_one_line_summary_in_the_sidecar(self):
        inline = [(inline_label(event, matcher, cond), hook.get("command", ""))
                  for event, matcher, cond, hook in registrations()
                  if hook.get("type") == "command" and command_script(hook) is None]
        self.assertTrue(inline, "no inline command in settings.json, so the scan proves nothing: "
                                "the SessionStart startup|resume refresh must stay inline (F1 ruling)")
        self.assertTrue(os.path.isfile(INLINE_JSON), "lint/hook_catalog_inline.json does not exist")
        summaries = json.loads(read(INLINE_JSON))
        rows = {r["Key"].strip("`"): r for r in page_rows(self.page()) if r["Kind"] == "hook"}
        problems, keys = [], set()
        for label, command in inline:
            key = sidecar_key(label, command)
            keys.add(key)
            text = summaries.get(key)
            if not isinstance(text, str) or not text.strip():
                problems.append("%s: no summary under the key %r in lint/hook_catalog_inline.json" % (label, key))
                continue
            if "\n" in text or text != text.strip():
                problems.append("%s: summary is not one trimmed line" % label)
            row = rows.get("inline: " + label)
            if row is None:
                problems.append("%s: no row keyed 'inline: %s'" % (label, label))
            elif row["What it does"] != " ".join(text.split()):
                problems.append("%s: row text %r is not the summary %r" % (label, row["What it does"], text))
        for stray in sorted(set(summaries) - keys):
            problems.append("%s: sidecar key matches no inline command" % stray)
        self.assertFalse(problems, "\n".join(problems))

    def test_r2_every_prompt_judge_has_a_row_keyed_by_its_first_sentence(self):
        rows = page_rows(self.page())
        problems, seen = [], 0
        for label, hook in judge_hooks():
            seen += 1
            found = LABEL.match(label)
            event, matcher, cond = found.group(1), found.group(2) or "-", found.group(3) or "-"
            key = first_sentence(hook.get("prompt", ""))
            if not key:
                problems.append("%s: prompt has no first sentence" % label)
            elif not any(r["Kind"] == "judge" and r["Key"].strip("`") == key
                         and (r["Event"], r["Matcher"], r["If"]) == (event, matcher, cond) for r in rows):
                problems.append("%s: no judge row keyed by %r" % (label, key))
        self.assertTrue(seen, "no prompt hook found, so the scan proves nothing")
        self.assertFalse(problems, "\n".join(problems))

    def test_r3_every_enabled_repo_mod_has_a_row(self):
        plugins = json.loads(read(SETTINGS)).get("enabledPlugins", {})
        mods = sorted(k.split("@")[0] for k, on in plugins.items()
                      if on is True and k.endswith("@claude-settings"))
        self.assertTrue(mods, "no enabled @claude-settings mod, so the scan proves nothing")
        keys = {r["Key"].strip("`") for r in page_rows(self.page()) if r["Kind"] == "mod"}
        missing = ["mods/" + m for m in mods if "mods/" + m not in keys]
        self.assertFalse(missing, "no mod row for: " + ", ".join(missing))

    def test_r4_every_skill_folder_has_a_row_that_says_no_model(self):
        names = skill_names()
        self.assertTrue(names, "no skill folder, so the scan proves nothing")
        by_key = {r["Key"].strip("`"): r for r in page_rows(self.page()) if r["Kind"] == "skill"}
        problems = []
        for name in names:
            row = by_key.get("skills/" + name)
            if row is None:
                problems.append("no skill row for skills/%s" % name)
            elif row["Model"] != "no model":
                problems.append("skills/%s: Model %r, want 'no model'" % (name, row["Model"]))
        self.assertFalse(problems, "\n".join(problems))

    def test_r5_one_row_per_registration_and_no_stale_hook_row(self):
        want = collections.Counter()
        for event, matcher, cond, hook in registrations():
            if hook.get("type") == "command":
                key = command_script(hook) or "inline: " + inline_label(event, matcher, cond)
                want[(key, event, matcher, cond)] += 1
            elif hook.get("type") == "prompt":
                want[(first_sentence(hook.get("prompt", "")), event, matcher, cond)] += 1
        self.assertTrue(want, "no registration found, so the scan proves nothing")
        got = collections.Counter(
            (r["Key"].strip("`"), r["Event"], r["Matcher"], r["If"])
            for r in page_rows(self.page()) if r["Kind"] in ("hook", "judge"))
        missing, extra = want - got, got - want
        problems = ["missing row: %r" % (k,) for k in missing] + ["stale row: %r" % (k,) for k in extra]
        self.assertFalse(problems, "\n".join(problems))

    def test_r5b_every_hook_judge_mod_and_skill_row_is_filled_in(self):
        problems = []
        for r in page_rows(self.page()):
            name = r["Key"] or "(no key)"
            if r["Kind"] in ("hook", "judge"):
                if r["Event"] in ("", "-"):
                    problems.append("%s: no event" % name)
                if not r["Matcher"]:
                    problems.append("%s: matcher cell empty (write - when absent)" % name)
            for col in ("Model", "Effort", "What it does"):
                if not r[col]:
                    problems.append("%s: %s is empty" % (name, col))
        self.assertFalse(problems, "\n".join(problems))

    def test_r6_model_and_effort_match_settings_and_the_model_table(self):
        rows = {}
        for r in page_rows(self.page()):
            if r["Kind"] in ("hook", "judge"):
                rows[(r["Key"].strip("`"), r["Event"], r["Matcher"], r["If"])] = r
        table = table_rows()
        problems = []
        for event, matcher, cond, hook in registrations():
            if hook.get("type") == "command":
                path = command_script(hook)
                key = (path or "inline: " + inline_label(event, matcher, cond), event, matcher, cond)
                want_model, want_effort = table.get(path, ("no model", "n/a"))
            elif hook.get("type") == "prompt":
                key = (first_sentence(hook.get("prompt", "")), event, matcher, cond)
                want_model, want_effort = hook.get("model", ""), "n/a"
            else:
                continue
            row = rows.get(key)
            if row is None:
                continue  # R5 names the missing row
            if not model_matches(row["Model"], want_model):
                problems.append("%r: Model %r, want %r" % (key, row["Model"], want_model))
            if row["Effort"] != want_effort:
                problems.append("%r: Effort %r, want %r" % (key, row["Effort"], want_effort))
        for path in sorted(invoke_model_callers() - set(table)):
            problems.append("%s calls invoke_model but has no model-table row" % path)
        self.assertFalse(problems, "\n".join(problems))

    def test_r7_committed_page_equals_generator_output(self):
        code, out, err = generator(ROOT, "--print")
        self.assertEqual(code, 0, out + err)
        committed = self.page().replace("\r\n", "\n")
        self.assertEqual(committed, out.replace("\r\n", "\n"),
                         "docs/catalog.md is stale: run python3 lint/hook_catalog.py")

    def test_r8_the_ci_check_passes_on_this_repo(self):
        code, out, err = generator(None, "--check")
        self.assertEqual((code, out + err), (0, ""), out + err)

    def test_r9_session_start_refresh_command_is_byte_identical_to_main(self):
        # F1 ruling: the refresh stays inline. A move into a script gates recovery on an install.
        # Equal as the JSON decodes, which is the exact text the harness runs.
        commands = [hook.get("command") for event, matcher, _cond, hook in registrations()
                    if event == "SessionStart" and matcher == "startup|resume" and hook.get("type") == "command"]
        self.assertIn(MAIN_SESSION_REFRESH, commands,
                      "no SessionStart startup|resume command is byte-identical to the refresh on origin/main")


# ---- fixtures: the generator on temp trees ----------------------------------------------------

TABLE_TEXT = """# Model table

| Point | Model | Effort |
|---|---|---|
| every other hook and gate | no model; plain code | n/a |
| skill `alpha` | no model pin; runs on the caller's model | none |
| judge (`hooks/ok_judge.py`) | haiku, through `decision_watch.invoke_model` | xhigh |
"""


def command(path):
    return {"type": "command",
            "command": 'g="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/%s"; [ -f "$g" ] || exit 0; exec python3 "$g"' % path}


def judge(prompt="Judge this AskUserQuestion call: $ARGUMENTS\nAnswer ok.", model="claude-sonnet-5-5"):
    return {"type": "prompt", "model": model, "prompt": prompt}


def skill_md(frontmatter, body="Body text.\n"):
    return "---\nname: alpha\n%s\n---\n\n%s" % (frontmatter, body)


def files(hooks=None, plugins=None, extra=None):
    out = {
        "settings.json": json.dumps({"hooks": hooks or {}, "enabledPlugins": plugins or {}}),
        "decisions/subagent-model-cap.md": TABLE_TEXT,
        "skills/alpha/SKILL.md": skill_md("description: Use when testing alpha."),
    }
    out.update(extra or {})
    return out


CLEAN_HOOKS = {
    "Stop": [{"hooks": [command("hooks/ok.py"), command("hooks/ok_judge.py")]}],
    "PreToolUse": [{"matcher": "AskUserQuestion", "hooks": [judge()]}],
}


def clean():
    return files(hooks=CLEAN_HOOKS, plugins={"tw@claude-settings": True}, extra={
        "hooks/ok.py": '"""Does one thing, plainly."""\nprint("ok")\n',
        "hooks/ok_judge.py": '"""Judges one thing."""\nfrom decision_watch import invoke_model\ninvoke_model("x")\n',
        "mods/tw/.claude-plugin/plugin.json": "{}\n",
        "mods/tw/README.md": "# tw\n\nA mod that does one thing.\n",
    })


def put(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def row_for(rows, key):
    for r in rows:
        if r["Key"].strip("`") == key:
            return r
    raise AssertionError("no row keyed %s in the page" % key)


class Fixtures(unittest.TestCase):
    def tree(self, tree_files):
        root = tempfile.mkdtemp(prefix="hook_catalog_")
        self.addCleanup(shutil.rmtree, root, True)
        for rel, text in tree_files.items():
            put(root, rel, text)
        return root

    def assert_problem(self, tree_files, *names):
        code, out, err = generator(self.tree(tree_files), "--check")
        self.assertEqual(code, 1, out + err)
        for name in names:
            self.assertIn(name, out + err)

    def rows_of(self, tree_files):
        code, out, err = generator(self.tree(tree_files), "--print")
        self.assertEqual(code, 0, out + err)
        return page_rows(out)

    def test_f1_script_with_no_docstring_fails(self):
        self.assert_problem(files(hooks={"Stop": [{"hooks": [command("hooks/nodoc.py")]}]},
                                  extra={"hooks/nodoc.py": "import os\nprint(os.name)\n"}),
                            "hooks/nodoc.py", "docstring")

    def test_f2_shell_first_code_line_is_not_a_docstring(self):
        self.assert_problem(files(hooks={"Stop": [{"hooks": [command("hooks/shdoc.sh")]}]},
                                  extra={"hooks/shdoc.sh": 'echo "# x"\n'}),
                            "hooks/shdoc.sh", "docstring")

    def test_f3_shell_lone_quote_survives_in_the_docstring(self):
        rows = self.rows_of(files(hooks={"Stop": [{"hooks": [command("hooks/quote.sh")]}]},
                                  extra={"hooks/quote.sh": "# Don't block the session.\necho ok\n"}))
        self.assertIn("Don't block the session.", row_for(rows, "hooks/quote.sh")["What it does"])

    def test_f4_shell_heredoc_after_the_comment_block_is_not_docstring(self):
        rows = self.rows_of(files(hooks={"Stop": [{"hooks": [command("hooks/heredoc.sh")]}]},
                                  extra={"hooks/heredoc.sh": "# Real doc.\ncat <<EOF\n# not doc\nEOF\n"}))
        what = row_for(rows, "hooks/heredoc.sh")["What it does"]
        self.assertIn("Real doc.", what)
        self.assertNotIn("not doc", what)

    def test_f5_shell_multi_line_string_opened_in_code_is_not_docstring(self):
        self.assert_problem(files(hooks={"Stop": [{"hooks": [command("hooks/multi.sh")]}]},
                                  extra={"hooks/multi.sh": 'MSG="start\n# inside string\nend"\n'}),
                            "hooks/multi.sh", "docstring")

    def test_f6_python_string_after_an_import_is_not_docstring(self):
        self.assert_problem(files(hooks={"Stop": [{"hooks": [command("hooks/late.py")]}]},
                                  extra={"hooks/late.py": 'import os\n"""Not the docstring."""\n'}),
                            "hooks/late.py", "docstring")

    def test_f7_prompt_hook_with_empty_prompt_fails(self):
        self.assert_problem(files(hooks={"PreToolUse": [{"matcher": "Bash", "hooks": [judge(prompt="")]}]}),
                            "PreToolUse", "Bash")

    def test_f8_enabled_repo_mod_without_source_fails(self):
        self.assert_problem(files(plugins={"tw@claude-settings": True},
                                  extra={"mods/tw/.claude-plugin/plugin.json": "{}\n"}),
                            "tw")

    def test_f9_skill_without_description_fails(self):
        self.assert_problem(files(extra={"skills/alpha/SKILL.md": "---\nname: alpha\n---\n\nBody.\n"}),
                            "alpha", "description")

    def test_f10_skill_with_empty_description_fails(self):
        self.assert_problem(files(extra={"skills/alpha/SKILL.md": "---\nname: alpha\ndescription:\n---\n\nBody.\n"}),
                            "alpha", "description")

    def test_f11_folded_description_reads_every_line(self):
        rows = self.rows_of(files(extra={"skills/alpha/SKILL.md": skill_md(
            "description: >\n  Use when testing\n  alpha in folded form.")}))
        self.assertIn("Use when testing alpha in folded form.",
                      row_for(rows, "skills/alpha")["What it does"])

    def test_f12_quoted_description_keeps_colon_space(self):
        rows = self.rows_of(files(extra={"skills/alpha/SKILL.md": skill_md(
            'description: "Use when: CI is slow."')}))
        self.assertIn("Use when: CI is slow.", row_for(rows, "skills/alpha")["What it does"])

    def test_f13_quoted_description_keeps_comment_openers(self):
        rows = self.rows_of(files(extra={"skills/alpha/SKILL.md": skill_md(
            'description: "Use for #tags and // paths."')}))
        self.assertIn("Use for #tags and // paths.", row_for(rows, "skills/alpha")["What it does"])

    def test_f14_lone_quote_in_plain_description_survives(self):
        rows = self.rows_of(files(extra={"skills/alpha/SKILL.md": skill_md(
            "description: Don't use this for CI.")}))
        self.assertIn("Don't use this for CI.", row_for(rows, "skills/alpha")["What it does"])

    def test_f15_rule_line_in_the_body_does_not_end_the_frontmatter(self):
        rows = self.rows_of(files(extra={"skills/alpha/SKILL.md": skill_md(
            "description: Real description.", body="Body.\n\n---\n\ndescription: Fake one.\n")}))
        what = row_for(rows, "skills/alpha")["What it does"]
        self.assertIn("Real description.", what)
        self.assertNotIn("Fake one.", what)

    def test_f16_argument_hint_with_pipes_and_brackets_does_not_break_the_read(self):
        rows = self.rows_of(files(extra={"skills/alpha/SKILL.md": skill_md(
            'argument-hint: "[a|b] [target]"\ndescription: Real description.')}))
        self.assertIn("Real description.", row_for(rows, "skills/alpha")["What it does"])

    def test_f17_script_calling_invoke_model_needs_its_own_table_row(self):
        self.assert_problem(files(hooks={"Stop": [{"hooks": [command("hooks/judge.py")]}]},
                                  extra={"hooks/judge.py": '"""Judge."""\nfrom decision_watch import invoke_model\ninvoke_model("x")\n'}),
                            "hooks/judge.py")

    def publish(self, root):
        """Write the generator's own render to docs/catalog.md, as a committed page would be."""
        code, out, err = generator(root, "--print")
        self.assertEqual(code, 0, out + err)
        put(root, "docs/catalog.md", out)

    def test_f18_stale_page_fails(self):
        root = self.tree(clean())
        self.publish(root)
        put(root, "hooks/ok.py", '"""Does another thing now."""\nprint("ok")\n')
        code, out, err = generator(root, "--check")
        self.assertEqual(code, 1, out + err)
        self.assertTrue("stale" in (out + err).lower() or "docs/catalog.md" in out + err, out + err)

    def test_f19_clean_tree_passes_silently(self):
        root = self.tree(clean())
        self.publish(root)
        self.assertEqual(generator(root, "--check"), (0, "", ""))

    def test_f20_settings_json_unreadable_exits_2_and_names_it(self):
        tree_files = clean()
        del tree_files["settings.json"]
        code, out, err = generator(self.tree(tree_files), "--check")
        self.assertEqual(code, 2, out + err)
        self.assertIn("settings.json", out + err)

    def test_f21_skill_whose_description_is_only_a_comment_fails(self):
        self.assert_problem(files(extra={"skills/alpha/SKILL.md": skill_md("description: #")}),
                            "alpha", "description")

    def test_f22_mod_with_empty_readme_fails(self):
        self.assert_problem(files(plugins={"tw@claude-settings": True}, extra={
            "mods/tw/.claude-plugin/plugin.json": "{}\n",
            "mods/tw/README.md": "# tw\n\n",
        }), "tw")


# ---- helper cases: these pass today and pin the readers the cases above rely on ---------------

    def test_f23_inline_command_with_no_summary_fails_check(self):
        hooks = dict(CLEAN_HOOKS)
        hooks["Notification"] = [{"hooks": [{"type": "command", "command": "echo inline-with-no-summary"}]}]
        spec = clean()
        spec["settings.json"] = json.dumps({"hooks": hooks, "enabledPlugins": {"tw@claude-settings": True}})
        code, out, err = generator(self.tree(spec), "--check")
        text = out + err
        self.assertEqual(code, 1, text)
        self.assertNotIn("Traceback", text)
        lines = [line for line in text.splitlines() if line.startswith("Notification")]
        self.assertTrue(any("summary" in line for line in lines), text)

    def test_f24_inline_command_with_a_summary_renders_it(self):
        command = "echo inline-with-summary"
        hooks = dict(CLEAN_HOOKS)
        hooks["Notification"] = [{"hooks": [{"type": "command", "command": command}]}]
        spec = clean()
        spec["settings.json"] = json.dumps({"hooks": hooks, "enabledPlugins": {"tw@claude-settings": True}})
        spec["lint/hook_catalog_inline.json"] = json.dumps({sidecar_key("Notification", command): "Says one plain thing."})
        row = row_for(self.rows_of(spec), "inline: Notification")
        self.assertEqual(row["What it does"], "Says one plain thing.")
        self.assertEqual((row["Event"], row["Model"], row["Effort"]), ("Notification", "no model", "n/a"))

    # Round 2 cases, F25-F29. The sidecar key is the label, " #", and 8 hex digits of the command's SHA-256.
    # F25 and F28 pin the builder's Modes and duplicate-key checks. F29 pins the orphan check.

    def test_f25_one_script_under_two_flags_does_not_share_one_summary(self):
        # A script registered twice with different flags. Under exit 0 the two rows may not show the
        # same text. Refusing, with the script named, is also allowed: a page cannot tell which mode.
        hooks = {"Stop": [{"hooks": [{"type": "command", "command": command("hooks/modes.py")["command"] + " " + flag}]}
                          for flag in ("--nudge", "--reorient")]}
        root = self.tree(files(hooks=hooks, extra={
            "hooks/modes.py": '"""Hands off the session on --nudge, and reorients the agent on --reorient."""\nimport sys\nprint(sys.argv)\n'}))
        code, out, err = generator(root, "--print")
        if code != 0:
            self.assertIn("hooks/modes.py", out + err, out + err)
            return
        rows = [r for r in page_rows(out) if r["Key"].strip("`") == "hooks/modes.py"]
        self.assertEqual(len(rows), 2, out + err)
        self.assertNotEqual(rows[0]["What it does"], rows[1]["What it does"],
                            "both registrations show one summary: " + rows[0]["What it does"])

    def test_f26_changed_inline_command_fails_check_until_its_summary_is_keyed(self):
        # Ruling: a changed command changes its sidecar key. --check fails, and names the new key, until a
        # person reviews the summary and keys it to the new text. Then the page matches and the check passes.
        def settings(text):
            hooks = dict(CLEAN_HOOKS, Notification=[{"hooks": [{"type": "command", "command": text}]}])
            return json.dumps({"hooks": hooks, "enabledPlugins": {"tw@claude-settings": True}})
        spec = clean()
        spec["settings.json"] = settings("echo one")
        spec["lint/hook_catalog_inline.json"] = json.dumps({sidecar_key("Notification", "echo one"): "Says one plain thing."})
        root = self.tree(spec)
        code, out, err = generator(root, "--print")
        self.assertEqual(code, 0, out + err)
        put(root, "docs/catalog.md", out)
        put(root, "settings.json", settings("echo two-changed"))
        new_key = sidecar_key("Notification", "echo two-changed")
        code, out, err = generator(root, "--check")
        self.assertEqual(code, 1, out + err)
        self.assertIn(new_key, out + err)
        put(root, "lint/hook_catalog_inline.json", json.dumps({new_key: "Says one plain thing."}))
        code, out, err = generator(root, "--print")
        self.assertEqual(code, 0, out + err)
        put(root, "docs/catalog.md", out)
        self.assertEqual(generator(root, "--check"), (0, "", ""))

    def test_f27_two_inline_commands_under_one_label_both_carry_summaries(self):
        # Two inline commands, same event, matcher and if. Their labels match, so their hash keys tell them
        # apart. Each must carry its own summary, and the page must check green.
        hooks = dict(CLEAN_HOOKS, Notification=[{"hooks": [
            {"type": "command", "command": "echo first"}, {"type": "command", "command": "echo second"}]}])
        spec = clean()
        spec["settings.json"] = json.dumps({"hooks": hooks, "enabledPlugins": {"tw@claude-settings": True}})
        spec["lint/hook_catalog_inline.json"] = json.dumps({
            sidecar_key("Notification", "echo first"): "First summary.",
            sidecar_key("Notification", "echo second"): "Second summary."})
        root = self.tree(spec)
        code, out, err = generator(root, "--print")
        self.assertEqual(code, 0, out + err)
        got = sorted(r["What it does"] for r in page_rows(out) if r["Kind"] == "hook" and r["Event"] == "Notification")
        self.assertEqual(got, ["First summary.", "Second summary."], out + err)
        put(root, "docs/catalog.md", out)
        self.assertEqual(generator(root, "--check"), (0, "", ""))

    def test_f28_duplicate_sidecar_key_fails_check(self):
        # json.loads keeps the last of two equal keys without a word. The file then says two things.
        command = "echo one"
        key = sidecar_key("Notification", command)
        hooks = dict(CLEAN_HOOKS, Notification=[{"hooks": [{"type": "command", "command": command}]}])
        spec = clean()
        spec["settings.json"] = json.dumps({"hooks": hooks, "enabledPlugins": {"tw@claude-settings": True}})
        spec["lint/hook_catalog_inline.json"] = '{"%s": "First summary.", "%s": "Second summary."}' % (key, key)
        root = self.tree(spec)
        _code, out, err = generator(root, "--print")
        put(root, "docs/catalog.md", out)
        code, out, err = generator(root, "--check")
        self.assertEqual(code, 1, out + err)
        self.assertIn(key, out + err)
        self.assertNotIn("Traceback", out + err)

    def test_f29_orphan_sidecar_key_fails_check(self):
        # Guard: an entry that names no inline command fails --check, and the message names the key.
        hooks = dict(CLEAN_HOOKS, Notification=[{"hooks": [{"type": "command", "command": "echo one"}]}])
        spec = clean()
        spec["settings.json"] = json.dumps({"hooks": hooks, "enabledPlugins": {"tw@claude-settings": True}})
        spec["lint/hook_catalog_inline.json"] = json.dumps(
            {sidecar_key("Notification", "echo one"): "Says one plain thing.", "PreToolUse matcher=Gone #00000000": "Orphan."})
        self.assert_problem(spec, "PreToolUse matcher=Gone")


class Helpers(unittest.TestCase):
    def test_u1_escaped_pipe_in_a_code_span_stays_in_its_cell(self):
        self.assertEqual(split_cells("| `Bash\\|PowerShell` | x |"), ["`Bash|PowerShell`", "x"])

    def test_u2_first_sentence_cuts_at_the_newline(self):
        self.assertEqual(first_sentence("Judge this edit to a file: $ARGUMENTS\nRule: x."),
                         "Judge this edit to a file: $ARGUMENTS")

    def test_u3_first_sentence_keeps_its_period(self):
        self.assertEqual(first_sentence("Rule one. Rule two."), "Rule one.")

    def test_u4_page_rows_reads_only_tables_with_the_catalog_header(self):
        text = ("| Other | Table |\n|---|---|\n| a | b |\n\n"
                "| Key | Kind | Event | Matcher | If | Model | Effort | What it does |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| `hooks/x.py` | hook | Stop | - | - | no model | n/a | Does x. |\n")
        rows = page_rows(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Key"], "`hooks/x.py`")


if __name__ == "__main__":
    unittest.main()
