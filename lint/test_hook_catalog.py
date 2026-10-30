#!/usr/bin/env python3
"""Cases for lint/hook_catalog.py: the generated page of hooks, prompt judges, mods and skills.

Run: python3 lint/test_hook_catalog.py -v

One readable page says, for each hook, judge and mod, what it does and which model and effort
it runs on. The page is generated, never kept by hand. Skills are in scope too. Their source is
the frontmatter description.

Interface the generator must meet.
- lint/hook_catalog.py, stdlib only, Python 3.11. Root: the repo root, or env HOOK_CATALOG_ROOT
  (same layout). Every fixture case sets HOOK_CATALOG_ROOT to a temp tree.
- No argument: write docs/catalog.md. `--print`: write the render to stdout, exit 1 while a problem
  stands (the problems go to stderr), else exit 0. stdout is UTF-8 whatever the console codepage.
- `--check`: exit 0 and print nothing when docs/catalog.md equals the render (CRLF normalized).
  Exit 1: one line per problem, naming the offender (stale page, empty source, missing row).
  Exit 2: the path of an input it cannot read (settings.json, the model table, a file it names).
- A description cell (What it does) longer than CELL_CAP characters is cut to at most CELL_CAP
  characters and ends in an ellipsis (U+2026). CELL_CAP is a named constant in lint/hook_catalog.py.
  A cut never splits a backtick span, and every row keeps its cells.
- Sources, read from the root:
  - settings.json `hooks`: one row per registration (event, matcher, `if`, command or prompt).
  - A command names its script as `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/<path>`. Source: a .py
    docstring (ast.get_docstring), or a .sh leading comment block after an optional shebang, which
    stops at the first other line. No docstring is a problem.
  - A command that names no script is inline. Its text is the one-line value in
    lint/hook_catalog_inline.json under its sidecar key: its label (the event, then ` matcher=<m>` and
    ` if=<c>` when present), then ` #` and the first 8 hex digits of the SHA-256 of the command text
    (a changed command changes its key, so it fails --check until its summary is keyed).
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

Real-repo cases R1-R9 read this repo.
Fixture cases F1-F29 run the generator on temp trees, so a generator that is silent for every
input fails them. F25 and F28 pin the Modes and duplicate-key checks, F26 and F27 pin
the hash-keyed sidecar, and F29 pins the orphan check.
Unit cases U1-U4 pin the table and sentence helpers used here.

Scanner rule: Python docstrings go through ast. The .sh header reader and the frontmatter reader
are hand scanners; they get the comment-opener, lone-quote and multi-line-string cases (F2-F6,
F11-F16). JavaScript is not scanned, so the multi-line template-literal case does not apply.

Records page: a live index for this and all repos. It deletes stale rulings and rewrites in place,
and never stores an overruled history. Cases A, B, C, D and R10-R13 pin it; U5-U7 pin the readers
they use. Interface the generator must meet. One home: the same generator, no second script.
- No argument writes every page it owns: docs/catalog.md and docs/records.md. `--check` checks both:
  a missing or stale page, or a problem, is exit 1 and names the page or the offender. `--print`
  stays the catalog page only (R7). F18, F19, F26 and F27 publish with a no-argument run.
- Merge-time rebuild. The shared merge tool (merge/merge.py,
  cases in merge/test_merge.py, class RecordsRebuild) rewrites the records page on the pull request
  head before it merges, the way it claims record numbers. So a pull request need not carry a fresh
  page. `--check` is mode-aware, as the stamp engine's check is (onDefaultBranch): on a pull request
  run (GITHUB_BASE_REF set, or GITHUB_REF under refs/pull/) a stale or missing docs/records.md is no
  failure and prints nothing. On any other run (a push to the default branch, a laptop) it fails and
  names the page. A problem (a history marker, an empty record, an unreadable file) and the catalog
  page stay red everywhere. Why keep the check: after a merge made without the tool, or a failed
  rebuild, main would hold a stale index and no signal. The push check on main is that signal, and the
  next merge heals it. Why lenient on a pull request: each pull request that touches a record would
  have to carry a regenerated page, and two of them conflict on it. R10-R13 read the committed page, so
  they are skipped on a pull request run. The fixture cases drop the runner's variables (B6-B10 set them).
- A root with no records at all (no record folder, no rule marker) writes no page: exit 0, nothing
  written, `--check` silent. The merge tool runs the generator on every repo it merges (D5).
- `--root DIR` is the repo root, the same as the environment variable HOOK_CATALOG_ROOT (both work).
  It never comes from the working folder.
- Catalog parts: a hooks/, skills/ or mods/ folder. A root with none writes and checks only
  docs/records.md and never reads settings.json or the model table. A root with a part and no
  settings.json is still exit 2 (F20).
- Records, read from the root: the `<!-- rule:<id> -->` markers in CLAUDE.md, and the .md files in
  decisions/, debts/ and plans/. A README.md in a folder is no record. Other files and a
  missing folder are ignored. A file the generator cannot read is exit 2 naming it. An empty record,
  or a debt with no What, is a problem: exit 1 naming the file.
- Page: one `## ` section per kind, in this order, only when it has a row: Mandates, Rulings, Build
  designs, Unsorted decisions, Debts, Plans. Each holds a table headed Slug | Gist | Link.
  Slug: the rule id, or the file name without .md. Link: `../CLAUDE.md` or `../<folder>/<slug>.md`.
  Rows: Mandates in CLAUDE.md order, every other kind sorted by slug. A pipe in a gist is written \\|.
- Rulings: Kind: process. Build designs: Kind: build. Unsorted decisions: no Kind line, or a Kind
  the generator does not know (that may instead be a problem naming the file). A Kind line counts
  outside fenced text only: a fenced example of both kinds counts for neither (the FENCED_KINDS fixture).
- Gist, one sentence, text flattened first (lines wrap). A sentence ends at ". ", "? " or "! ", or at
  the end of its block. Mandate: the first sentence of the rule's text, which runs from the paragraph
  start (a bold lead label dropped) or the marker before it, to its marker. Decision: the first block
  under the first `## Ruling` or `## The ruling`, else under `## The question`, else the first
  paragraph under the H1, else the H1 text. A list item is a block; its marker is dropped. Other
  text stays as written, so a decision whose paragraph opens with bold text (the real
  one-shared-record-stamp does) keeps it. Debt: the What. Plan: the first line, its
  leading # dropped. Frontmatter (A17-A24): a record that opens with `---` on line 1, key lines and a
  closing `---` gives its `title:` as the gist, quotes dropped, when it has no ruling, question or
  H1 to read. A title reads as a skill's `description` does: an escaped or doubled quote, a trailing
  comment and a `>` block scalar. Frontmatter with no title gives way to the H1. A `---` block below
  line 1 is prose, and so is a block that never closes.
  Not pinned: a title against a ruling, a question or an H1 in the same record.
- No overruled history. A marker is Superseded, Overruled, Previously, "was:", "no longer in force"
  or "Old ruling", in any case. The other five fail only where they open a block: the text of a
  heading, a paragraph, or a list item, after an optional list marker and emphasis marks around the
  marker itself. "was:" fails where it opens a block, or where the word "old" comes earlier in the
  same block ("the old wording was: ..."). A bare "no longer" is no marker. The failure is one line per
  offender, `<path>:<line>`, 1-based, forward slashes. CLAUDE.md, decisions/, debts/ and
  plans/ are read; a README.md is not. Fenced blocks and inline code are code, not read. HTML
  comments are not special: their lines are read as prose, so history hidden in a comment fails when
  it opens a block. A continuation line of a wrapped paragraph does not open a block.
  Why the marker must open a block: the plain rule "the marker appears anywhere in the prose" would
  fire on behaviour prose ("the guard no longer crashes"), CI runs ("cancels superseded runs"), and
  a rule quoted by name. That would cry wolf. The cost: kept history that says "(superseded by
  the floor, kept as evidence)" mid-sentence is not caught. A debt's What describing a gap may say
  "no longer", and it opens with its "**What.**" label.
- Scanner cases (rule building-scanner-respects-strings), the markdown form. A comment opener, a
  quote or a backtick inside code or a fence must not hide, or invent, a marker, a heading, a Kind
  line or a rule marker. A multi-line fenced block is the multi-line-template-literal case. A lone
  quote or backtick in text must not open a string.
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
TABLE = os.path.join(ROOT, "docs", "decisions", "agent-model-cap.md")
COLUMNS = ["Key", "Kind", "Event", "Matcher", "If", "Model", "Effort", "What it does"]
CMD_PATH = re.compile(r"\$\{CLAUDE_CONFIG_DIR:-\$HOME/\.claude\}/([\w./-]+\.(?:py|sh|mjs|js))")
TABLE_PATH = re.compile(r"`([\w./-]+\.(?:py|sh|mjs|js))`")
LABEL = re.compile(r"^(\S+)(?: matcher=(\S+))?(?: if=(.+))?$")

sys.path.insert(0, HERE)
from test_settings_matcher import SETTINGS, JUDGE_TYPES, judge_hooks  # noqa: E402  one home for settings.json, the judge walk and its hook types
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
    """The sidecar key of an inline command: its label, " #", then the first 8 hex digits
    of the SHA-256 of its command text. Written here from the spec, not imported from the generator."""
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


PR_ENV = ("GITHUB_BASE_REF", "GITHUB_REF", "GITHUB_EVENT_NAME")  # what Actions sets on a pull request run


def pull_request_run():
    """True when this test run is itself a pull request run in Actions (the stamp engine's test: onDefaultBranch)."""
    return bool(os.environ.get("GITHUB_BASE_REF")) or os.environ.get("GITHUB_REF", "").startswith("refs/pull/")


def generator(root, *args, cwd=None, flag_root=False, env=None):
    """Run lint/hook_catalog.py on root (None: the real repo). Returns (code, stdout, stderr).
    The root goes in the environment variable, or as --root DIR with flag_root. cwd: the working folder, root by default.
    env: variables to add. A fixture run (root given) drops the runner's pull request variables first, so a fixture
    behaves the same on a laptop and in a pull request run; the real repo (root None) keeps them."""
    if not os.path.exists(GEN):
        raise AssertionError("lint/hook_catalog.py does not exist yet: the builder writes it")
    child = dict(os.environ)
    child.pop("HOOK_CATALOG_ROOT", None)
    if root is not None:
        for name in PR_ENV:
            child.pop(name, None)
    child.update(env or {})
    env = child
    argv = [sys.executable, GEN, *args]
    if root is not None:
        if flag_root:
            argv += ["--root", root]
        else:
            env["HOOK_CATALOG_ROOT"] = root
    proc = subprocess.run(argv, cwd=cwd or root or ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


# Text markers the SessionStart refresh must keep: the remote exit, the fast-forward-only move of
# main, and the pin helper it runs. It must not contain stash, reset, switch, checkout, --force or a
# force refspec. Behaviour is pinned by the cases in merge/test_install_from_main.sh; no case runs
# those words, so this text lint is the only guard on them.
SESSION_REFRESH_MUST = (
    '[ -n "$CLAUDE_CODE_REMOTE" ] && exit 0',
    'refs/remotes/origin/main:refs/heads/main',
    'merge -q --ff-only origin/main',
    'merge/install_from_main.sh',
)
SESSION_REFRESH_MUST_NOT = ("stash", "reset", "switch", "checkout", "--force", "+refs/")


# ---- real repo -------------------------------------------------------------------------------


class RealRepo(unittest.TestCase):
    def page(self):
        if not os.path.exists(PAGE):
            self.fail("docs/catalog.md does not exist yet: the generator writes it")
        return read(PAGE)

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
            elif hook.get("type") in JUDGE_TYPES:
                want[(first_sentence(hook.get("prompt", "")), event, matcher, cond)] += 1
        self.assertTrue(want, "no registration found, so the scan proves nothing")
        got = collections.Counter(
            (r["Key"].strip("`"), r["Event"], r["Matcher"], r["If"])
            for r in page_rows(self.page()) if r["Kind"] in ("hook", "judge"))
        missing, extra = want - got, got - want
        problems = ["missing row: %r" % (k,) for k in missing] + ["stale row: %r" % (k,) for k in extra]
        self.assertFalse(problems, "\n".join(problems))
        # Each judge hook (prompt or agent) has a judge row keyed by its first sentence.
        # Named failure: a judge row that lost its key, so the page hides which judge runs.
        judge_page = page_rows(self.page())
        problems, seen = [], 0
        for label, hook in judge_hooks():
            seen += 1
            found = LABEL.match(label)
            event, matcher, cond = found.group(1), found.group(2) or "-", found.group(3) or "-"
            key = first_sentence(hook.get("prompt", ""))
            if not key:
                problems.append("%s: prompt has no first sentence" % label)
            elif not any(r["Kind"] == "judge" and r["Key"].strip("`") == key
                         and (r["Event"], r["Matcher"], r["If"]) == (event, matcher, cond) for r in judge_page):
                problems.append("%s: no judge row keyed by %r" % (label, key))
        # settings.json registers no prompt or agent hook now: every judge is a command hook, so no
        # override is out of reach. The scan finds none, and the page holds no judge row.
        self.assertEqual(seen, 0, "a prompt or agent hook is registered again: an owner override cannot lift it")
        self.assertEqual([r["Key"] for r in judge_page if r["Kind"] == "judge"], [], "stale judge row")
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

    def test_r9_session_start_refresh_has_its_text_markers(self):
        # A text lint, not a behaviour test. The refresh stays inline: a move into a script checks
        # recovery on an install.
        commands = [hook.get("command", "") for event, matcher, _cond, hook in registrations()
                    if event == "SessionStart" and matcher == "startup|resume" and hook.get("type") == "command"]
        refresh = [c for c in commands if "CLAUDE.md" in c]
        self.assertEqual(len(refresh), 1, "want one SessionStart startup|resume refresh that reads CLAUDE.md, found %d" % len(refresh))
        missing = [m for m in SESSION_REFRESH_MUST if m not in refresh[0]]
        found = [m for m in SESSION_REFRESH_MUST_NOT if m in refresh[0]]
        self.assertFalse(missing, "the SessionStart refresh lost: %s" % ", ".join(missing))
        self.assertFalse(found, "the SessionStart refresh now has: %s" % ", ".join(found))


# ---- fixtures: the generator on temp trees ----------------------------------------------------

TABLE_TEXT = """# Model table

| Point | Model | Effort |
|---|---|---|
| every other hook and guard | no model; plain code | n/a |
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
        "decisions/agent-model-cap.md": TABLE_TEXT,
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


# ---- the records page: readers and fixture texts ------------------------------------------------

RECORDS_COLUMNS = ["Slug", "Gist", "Link"]
SECTIONS = ["Mandates", "Rulings", "Build designs", "Unsorted decisions", "Debts", "Plans"]
RECORDS_PAGE = os.path.join(ROOT, "docs", "records.md")
LINK_TARGET = re.compile(r"\]\(([^)]*)\)")
RULE_MARK = re.compile(r"<!--\s*rule:([a-z0-9][a-z0-9-]*)\s*-->")
KIND_LINE = re.compile(r"^Kind:\s*(process|build)\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def unfenced_lines(text):
    """Lines outside fenced blocks. A fence closes on the same character, at least as long, with no text after it.
    Written here from CommonMark, not imported from the generator."""
    fence = None
    for line in text.replace("\r\n", "\n").split("\n"):
        found = FENCE.match(line)
        if fence:
            if found and found.group(1)[0] == fence[0] and len(found.group(1)) >= len(fence) and not found.group(2).strip():
                fence = None
            continue
        if found and not (found.group(1)[0] == "`" and "`" in found.group(2)):
            fence = found.group(1)
            continue
        yield line


def records_rows(text):
    """Rows of every table headed Slug | Gist | Link, each a dict: section (the last '## ' heading above the
    table), slug (backticks off), gist (an escaped pipe unescaped) and link (the target of the first
    markdown link in the Link cell, or "")."""
    rows, section, state = [], "", None
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            section, state = line[3:].strip(), None
            continue
        if not line.lstrip().startswith("|"):
            state = None
            continue
        cells = split_cells(line)
        if state is None:
            if cells == RECORDS_COLUMNS:
                state = "separator"
            continue
        if state == "separator":
            state = "body"
            continue
        cells += [""] * len(RECORDS_COLUMNS)
        found = LINK_TARGET.search(cells[2])
        rows.append({"section": section, "slug": cells[0].strip("`"), "gist": cells[1],
                     "link": found.group(1) if found else ""})
    return rows


def listed(rows):
    """{section: [slug, ...]} in page order."""
    out = {}
    for r in rows:
        out.setdefault(r["section"], []).append(r["slug"])
    return out


def line_of(text, line):
    """The 1-based number of the first line of text that equals line."""
    return text.split("\n").index(line) + 1


RULED = ("# Ruled thing\n\n## The question\n\nWhat is ruled?\n\n## The ruling\n\n"
         "The thing is ruled. More text follows.\n\nKind: process\n")
BUILT = ("# Built thing\n\n## The question\n\nHow is the thing built? Plainly.\n\n"
         "Kind: build\nPlan: plans/plan-a.md#plan-a (linux)\n")
LOOSE = ("# Loose note\n\nThis note has no kind and no\nruling heading. It wraps across lines.\n\n"
         "## Why\n\nBecause.\n")
TITLED = "# Just a title\n\n## Why\n\nBecause.\n"
DEBT = ("# Gap one\n\n- **What.** The check misses one case. It also misses a second.\n"
        "- **Where.** `lint/x.py`.\n- **Decision.** none\n- **Retire.** Cover both.\n")
PLAN = "# Plan: do a thing\n\nOne command does it.\n"
RULES = ("# How I work\n\n**Building.** Never guess an answer the code should give you.<!-- rule:b-one --> "
         "Surface ambiguity instead\nof resolving it silently. Say why.<!-- rule:b-two -->\n\n"
         "Never drop an item without saying so.<!-- rule:b-three -->\n")


def with_records(extra=None):
    """clean() (a catalog that passes) plus one record of each kind. extra: {path: text}; a None drops the path."""
    spec = clean()
    spec.update({"CLAUDE.md": RULES, "decisions/ruled.md": RULED, "decisions/built.md": BUILT,
                 "decisions/loose.md": LOOSE, "decisions/titled.md": TITLED, "debts/gap-one.md": DEBT,
                 "plans/plan-a.md": PLAN})
    for rel, text in (extra or {}).items():
        if text is None:
            spec.pop(rel, None)
        else:
            spec[rel] = text
    return spec


def lean(extra=None):
    """A repo with no catalog part: decisions/ and debts/ only."""
    spec = {"decisions/ruled.md": RULED, "decisions/built.md": BUILT, "decisions/loose.md": LOOSE,
            "debts/gap-one.md": DEBT, "debts/README.md": "# Debts\n\nOne file per debt.\n"}
    spec.update(extra or {})
    return spec


def old_decision(body, title="# Old thing"):
    """A decision whose body sits on line 7, after a blank line."""
    return "%s\n\n## The question\n\nWhat is it?\n\n%s\n" % (title, body)


class Tree(unittest.TestCase):
    """Cases that build a temp tree and run the generator on it. Holds no test of its own."""

    def tree(self, tree_files):
        root = tempfile.mkdtemp(prefix="hook_catalog_")
        self.addCleanup(shutil.rmtree, root, True)
        for rel, text in tree_files.items():
            put(root, rel, text)
        return root

    def publish(self, root):
        """Write every page the generator owns, as a committed repo would hold them: a no-argument run."""
        code, out, err = generator(root)
        self.assertEqual(code, 0, out + err)

    def records_text(self, root):
        """docs/records.md under root. A failure, not an error, while the generator has not written it."""
        path = os.path.join(root, "docs", "records.md")
        if not os.path.exists(path):
            self.fail("docs/records.md was not written")
        return read(path)


class Fixtures(Tree):
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
        # Rows: no description key, an empty value, a comment-only value.
        # Named failure: a skill with no usable description passes the page check.
        cases = [
            ("no key", "---\nname: alpha\n---\n\nBody.\n"),
            ("empty value", "---\nname: alpha\ndescription:\n---\n\nBody.\n"),
            ("comment only", skill_md("description: #")),
        ]
        for case, text in cases:
            with self.subTest(case):
                self.assert_problem(files(extra={"skills/alpha/SKILL.md": text}), "alpha", "description")

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

    # Cases F25-F29. The sidecar key is the label, " #", and 8 hex digits of the command's SHA-256.
    # F25 and F28 pin the Modes and duplicate-key checks. F29 pins the orphan check.

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
        # A changed command changes its sidecar key. --check fails, and names the new key, until a
        # person reviews the summary and keys it to the new text. Then the page matches and the check passes.
        def settings(text):
            hooks = dict(CLEAN_HOOKS, Notification=[{"hooks": [{"type": "command", "command": text}]}])
            return json.dumps({"hooks": hooks, "enabledPlugins": {"tw@claude-settings": True}})
        spec = clean()
        spec["settings.json"] = settings("echo one")
        spec["lint/hook_catalog_inline.json"] = json.dumps({sidecar_key("Notification", "echo one"): "Says one plain thing."})
        root = self.tree(spec)
        self.publish(root)
        put(root, "settings.json", settings("echo two-changed"))
        new_key = sidecar_key("Notification", "echo two-changed")
        code, out, err = generator(root, "--check")
        self.assertEqual(code, 1, out + err)
        self.assertIn(new_key, out + err)
        put(root, "lint/hook_catalog_inline.json", json.dumps({new_key: "Says one plain thing."}))
        self.publish(root)
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
        self.publish(root)
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


# ---- the records page: the generator on temp trees ---------------------------------------------

GIST_CASES = [
    ("ruling beats question", "# T\n\n## The question\n\nWhat?\n\n## The ruling\n\nIt is so. Yes.\n\nKind: process\n",
     "It is so."),
    ("plain Ruling heading", "# T\n\n## Ruling\n\nIt is so. Yes.\n\nKind: process\n", "It is so."),
    ("question only", "# T\n\n## The question\n\nHow does it work? It does.\n\nKind: process\n", "How does it work?"),
    ("a sentence that wraps", "# T\n\n## The ruling\n\nThe ruling wraps\nacross two lines. Then it ends.\n\nKind: process\n",
     "The ruling wraps across two lines."),
    ("list item first", "# T\n\n## The ruling\n\n- The installer writes each file first. Then it renames.\n- Second item.\n\nKind: process\n",
     "The installer writes each file first."),
    ("lone quote", "# T\n\n## The ruling\n\nDon't block the session. Ever.\n\nKind: process\n", "Don't block the session."),
    ("quoted ruling that ends its block", '# T\n\n## The ruling\n\nOwner ruling, 2026-10-13 23:41 CDT: "End condition at start."\n\n- A call needs a note.\n\nKind: process\n',
     'Owner ruling, 2026-10-13 23:41 CDT: "End condition at start."'),
    ("a heading inside a fence is no heading", "# T\n\n```\n## The ruling\n\nFake ruling. No.\n```\n\n## The question\n\nReal question?\n\nKind: process\n",
     "Real question?"),
    ("a first paragraph that opens with bold text keeps it", "# T\n\n**Changed in part on 2026-09-28** by `other-rule`, the rule stays. Second.\n\nKind: process\n",
     "**Changed in part on 2026-09-28** by `other-rule`, the rule stays."),
]

# A record with a fenced example of both kinds, then one real line: only the unfenced Kind line counts.
FENCED_KINDS = ("# T\n\n## The ruling\n\nIt is so.\n\n```\nKind: build\nPlan: <path>#<slug> (<platform>)\n\n"
                "Kind: process\nHome: rule:<id>\n```\n\nKind: process\nHome: lint/x.py\n")


# The tail of a record in q_max's shape: YAML frontmatter comes first (fm_record), then a refs fence,
# the Kind and Home lines, and plain prose with no H1.
FM_TAIL = ("\n```refs\nentries: D-070, D-479\n```\n\nKind: process\nHome: rule:git-main-only-by-pr\n\n"
           "The owner ruled on 2026-10-03, in chat: \"merge it\". The grant is one session's.\n\n"
           "No other session holds it.\n")


def fm_record(keys, tail=FM_TAIL):
    """A record that opens with a frontmatter block on line 1. keys: its lines, joined by newlines."""
    return "---\n%s\n---\n%s" % (keys, tail)


class RecordsPage(Tree):
    def rows(self, extra=None):
        root = self.tree(with_records(extra))
        self.publish(root)
        return records_rows(self.records_text(root))

    def test_a1_each_record_is_listed_once_under_its_kind(self):
        # The model table (decisions/agent-model-cap.md in the fixture) has no Kind line, so it is unsorted.
        self.assertEqual(listed(self.rows()), {
            "Mandates": ["b-one", "b-two", "b-three"],
            "Rulings": ["ruled"],
            "Build designs": ["built"],
            "Unsorted decisions": ["agent-model-cap", "loose", "titled"],
            "Debts": ["gap-one"],
            "Plans": ["plan-a"],
        })

    def test_a2_each_row_holds_a_one_sentence_gist(self):
        want = {
            ("Rulings", "ruled"): "The thing is ruled.",
            ("Build designs", "built"): "How is the thing built?",
            ("Unsorted decisions", "loose"): "This note has no kind and no ruling heading.",
            ("Unsorted decisions", "titled"): "Just a title",
            ("Debts", "gap-one"): "The check misses one case.",
            ("Plans", "plan-a"): "Plan: do a thing",
            ("Mandates", "b-one"): "Never guess an answer the code should give you.",
            ("Mandates", "b-two"): "Surface ambiguity instead of resolving it silently.",
            ("Mandates", "b-three"): "Never drop an item without saying so.",
        }
        got = {(r["section"], r["slug"]): r["gist"] for r in self.rows()}
        for key, gist in want.items():
            self.assertEqual(got.get(key), gist, key)

    def test_a3_each_row_links_to_its_file(self):
        folder = {"Rulings": "decisions", "Build designs": "decisions", "Unsorted decisions": "decisions",
                  "Debts": "debts", "Plans": "plans"}
        rows = self.rows()
        self.assertTrue(rows)
        for r in rows:
            want = "../CLAUDE.md" if r["section"] == "Mandates" else "../%s/%s.md" % (folder[r["section"]], r["slug"])
            self.assertEqual(r["link"], want, (r["section"], r["slug"]))

    def test_a4_rows_come_in_a_fixed_order(self):
        # Mandates in CLAUDE.md order, so a topic stays together. Every other kind sorted by slug, so a
        # Windows write and a Linux check agree whatever order the folder lists.
        got = listed(self.rows({
            "decisions/zeta.md": LOOSE, "decisions/alpha.md": LOOSE, "decisions/mid.md": LOOSE,
            "debts/z-gap.md": DEBT, "debts/a-gap.md": DEBT,
            "CLAUDE.md": "# R\n\nZ rule.<!-- rule:z-last -->\n\nA rule.<!-- rule:a-first -->\n"}))
        self.assertEqual(got["Mandates"], ["z-last", "a-first"])
        self.assertEqual(got["Unsorted decisions"], ["agent-model-cap", "alpha", "loose", "mid", "titled", "zeta"])
        self.assertEqual(got["Debts"], ["a-gap", "gap-one", "z-gap"])

    def test_a5_a_readme_and_a_non_markdown_file_are_no_records(self):
        got = listed(self.rows({"debts/README.md": "# Debts\n\nNo longer a store.\n\nSuperseded by nothing.\n",
                                "debts/notes.txt": "A note.\n", "decisions/.gitkeep": ""}))
        self.assertEqual(got["Debts"], ["gap-one"])
        self.assertNotIn("README", got["Debts"])

    def test_a6_one_slug_in_two_kinds_gets_two_rows(self):
        got = listed(self.rows({"decisions/shared.md": RULED, "debts/shared.md": DEBT}))
        self.assertIn("shared", got["Rulings"])
        self.assertIn("shared", got["Debts"])

    def test_a7_a_decision_gist_comes_from_its_ruling_else_its_question(self):
        extra = {"decisions/g%d.md" % i: text for i, (_name, text, _gist) in enumerate(GIST_CASES)}
        got = {r["slug"]: r["gist"] for r in self.rows(extra) if r["section"] == "Rulings"}
        for i, (name, _text, gist) in enumerate(GIST_CASES):
            with self.subTest(name):
                self.assertEqual(got.get("g%d" % i), gist)

    def test_a8_a_kind_line_counts_outside_fences_only(self):
        got = listed(self.rows({"decisions/fenced.md": FENCED_KINDS,
                                "decisions/only-fenced.md": "# T\n\nBody sentence.\n\n```\nKind: process\n```\n"}))
        self.assertIn("fenced", got["Rulings"])
        self.assertNotIn("fenced", got["Build designs"])
        self.assertIn("only-fenced", got["Unsorted decisions"])
        self.assertNotIn("only-fenced", got["Rulings"])

    def test_a9_a_kind_the_generator_does_not_know_is_unsorted_or_a_named_problem(self):
        root = self.tree(with_records({"decisions/odd.md": "# T\n\nBody sentence.\n\nKind: other\n"}))
        code, out, err = generator(root)
        if code != 0:
            self.assertEqual(code, 1, out + err)
            self.assertIn("decisions/odd.md", out + err)
            return
        self.assertIn("odd", listed(records_rows(self.records_text(root))).get("Unsorted decisions", []))

    def test_a10_a_rule_marker_in_code_or_a_fence_is_no_mandate(self):
        claude = ("# Rules\n\n**Scan.** Write `<!-- rule:fake-code -->` after each rule.<!-- rule:real-one -->\n\n"
                  "```text\n<!-- rule:fake-fence -->\n```\n\nDon't use a ` here.<!-- rule:after-tick -->\n")
        rows = [r for r in self.rows({"CLAUDE.md": claude}) if r["section"] == "Mandates"]
        self.assertEqual([r["slug"] for r in rows], ["real-one", "after-tick"])
        self.assertEqual(rows[0]["gist"], "Write `<!-- rule:fake-code -->` after each rule.")
        self.assertEqual(rows[1]["gist"], "Don't use a ` here.")

    def test_a11_a_gist_with_a_pipe_a_quote_and_comment_openers_stays_one_cell(self):
        what = "A pipe a|b and `c|d` stay, Don't break, // and # too, `<!-- x -->` as well."
        debt = DEBT.replace("The check misses one case. It also misses a second.", what)
        got = {(r["section"], r["slug"]): r["gist"] for r in self.rows({"debts/gap-one.md": debt})}
        self.assertEqual(got[("Debts", "gap-one")], what)

    def test_a12_crlf_and_a_bom_leave_no_mark_in_a_gist(self):
        debt = "﻿" + DEBT.replace("\n", "\r\n")
        got = {(r["section"], r["slug"]): r["gist"] for r in self.rows({"debts/gap-one.md": debt})}
        self.assertEqual(got[("Debts", "gap-one")], "The check misses one case.")

    def test_a13_a_record_with_no_text_is_a_problem_that_names_it(self):
        no_what = "# Gap\n\n- **Where.** `lint/x.py`.\n- **Decision.** none\n- **Retire.** Cover it.\n"
        for rel, text in (("debts/no-what.md", no_what), ("decisions/empty.md", "\n")):
            with self.subTest(rel):
                code, out, err = generator(self.tree(with_records({rel: text})))
                self.assertEqual(code, 1, out + err)
                self.assertIn(rel, out + err)
                self.assertNotIn("Traceback", out + err)

    def test_a14_a_record_that_cannot_be_read_is_exit_2_and_named(self):
        root = self.tree(with_records())
        with open(os.path.join(root, "decisions", "bad.md"), "wb") as handle:
            handle.write(b"# Bad\n\n\xff\xfe\x00 not utf-8\n")
        code, out, err = generator(root)
        self.assertEqual(code, 2, out + err)
        self.assertIn("decisions/bad.md", out + err)

    def test_a15_a_short_first_ruling_block_gives_the_question_sentence(self):
        # Kind: process throughout. A ruling's first block of under 4 words
        # ("Yes.", "Owner, 2026-10-11:") gives the first sentence of "## The question". A 4-word block stays (green pin).
        cases = [
            ("a bare yes", "Does the guard run first? It does.", "Yes.", "Does the guard run first?"),
            ("a 3-word block", "Is the page rebuilt at merge? Yes.", "Yes, it is.", "Is the page rebuilt at merge?"),
            ("a dated owner line, then a short block", "Is the page rebuilt at merge? Yes.",
             "Owner, 2026-10-11:\n\nYes.\n\nThe page is rebuilt at merge.", "Is the page rebuilt at merge?"),
            ("a 4-word block stays", "What runs first? The guard.", "The guard runs first.", "The guard runs first."),
        ]
        extra = {"decisions/r%d.md" % i: "# T\n\n## The question\n\n%s\n\n## The ruling\n\n%s\n\nKind: process\n" % (q, r)
                 for i, (_name, q, r, _gist) in enumerate(cases)}
        got = {r["slug"]: r["gist"] for r in self.rows(extra) if r["section"] == "Rulings"}
        for i, (name, _q, _r, gist) in enumerate(cases):
            with self.subTest(name):
                self.assertEqual(got.get("r%d" % i), gist)

    def test_a16_the_notes_file_in_debts_is_no_record(self):
        # A finding too unlikely to hit is one line in the notes file, not a debt. The notes file has no
        # **What.** line, and the page must not refuse it.
        notes = "# Notes\n\n- A finding too unlikely to hit. Decision: none.\n"
        root = self.tree(with_records({"debts/notes.md": notes}))
        code, out, err = generator(root)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(listed(records_rows(self.records_text(root)))["Debts"], ["gap-one"])

    def gist_of(self, rel, text):
        """The one gist the page holds for the record at rel. A generator that refuses the record fails the case,
        and its message names the file and the problem."""
        slug = os.path.basename(rel)[:-3]
        return {r["slug"]: r["gist"] for r in self.rows({rel: text})}[slug]

    def test_a17_a_frontmatter_title_is_the_gist(self):
        title = "The primary orchestrator alone holds a standing merge grant"
        text = fm_record("id: D-705\nslug: fm-title\ntitle: %s\ndate: 2026-10-03" % title)
        self.assertEqual(self.gist_of("decisions/fm-title.md", text), title)

    def test_a18_a_quoted_frontmatter_title_loses_its_quotes(self):
        # 211 of the 569 real q_max records quote the title. The gist must not carry the quotes.
        text = fm_record('id: D-504\nslug: fm-quoted\ntitle: "A band around 80, outside the tier"\ndate: 2026-09-23')
        self.assertEqual(self.gist_of("decisions/fm-quoted.md", text), "A band around 80, outside the tier")

    def test_a19_frontmatter_with_a_title_and_no_body_gives_the_title(self):
        text = fm_record("id: D-1\nslug: fm-bare\ntitle: A title with no body", tail="")
        self.assertEqual(self.gist_of("decisions/fm-bare.md", text), "A title with no body")

    def test_a20_frontmatter_with_no_title_falls_to_the_h1(self):
        # Green pin: with no title to read, the H1 rule holds as it does with no frontmatter.
        text = fm_record("id: D-9\nslug: fm-no-title\ndate: 2026-10-03",
                         tail="\n# The H1 text\n\nThe first paragraph under the H1. A second sentence.\n\nKind: process\n")
        self.assertEqual(self.gist_of("decisions/fm-no-title.md", text), "The first paragraph under the H1.")

    def assert_no_gist(self, records):
        """Each record {rel: text}, which holds no H1, ruling or question, lands in problems with no gist."""
        code, out, err = generator(self.tree(with_records(records)))
        said = out + err
        for rel in records:
            with self.subTest(rel):
                self.assertEqual(code, 1, said)
                self.assertIn("%s: no text to make a gist from" % rel, said)

    def test_a21_a_dashed_block_below_line_1_is_no_frontmatter(self):
        # A `---` block after other text is prose, and its title is no gist. The second record has a key line before
        # any `---`: the one shape that a missing line-1 guard would still read as a title.
        self.assert_no_gist({"decisions/fm-late.md": "Some prose.\n\n---\ntitle: x\n---\n",
                             "decisions/fm-key-first.md": "Some prose.\ntitle: x\n\n---\n"})

    def test_a22_a_title_with_comment_openers_and_a_lone_quote_stays_whole(self):
        # Scanner case (building-scanner-respects-strings): `//`, `/*` and `#` in a quoted title are text, and the
        # apostrophe in "Don't" opens no string.
        title = "Don't write // or /* or # in a title"
        text = fm_record('id: D-2\nslug: fm-openers\ntitle: "%s"' % title)
        self.assertEqual(self.gist_of("decisions/fm-openers.md", text), title)

    def test_a23_a_title_reads_as_the_shared_frontmatter_reader_reads_it(self):
        # frontmatter_description reads these same quote, comment and block-scalar forms in a skill's frontmatter.
        cases = [
            ("an escaped quote", 'title: "A pending market add reads \\"SLC New Market: Salt Lake City.\\""',
             'A pending market add reads "SLC New Market: Salt Lake City."'),
            ("a folded block scalar ends at the next key", "title: >\n  An indented title line", "An indented title line"),
            ("a trailing comment after a quoted title", 'title: "Foo" # note', "Foo"),
            ("a doubled single quote", "title: 'It''s'", "It's"),
        ]
        extra = {"decisions/fm-shared-%d.md" % i: fm_record("id: D-%d\n%s\ndate: 2026-10-03" % (i, keys))
                 for i, (_name, keys, _gist) in enumerate(cases)}
        got = {r["slug"]: r["gist"] for r in self.rows(extra)}
        for i, (name, _keys, gist) in enumerate(cases):
            with self.subTest(name):
                self.assertEqual(got.get("fm-shared-%d" % i), gist)

    def test_a24_a_block_that_closes_or_never_closes_gives_no_title(self):
        # The closing `---` ends the block, so a later `title:` line is body text. An unterminated block is no
        # frontmatter, as frontmatter_description reads it.
        self.assert_no_gist({"decisions/fm-closed.md": fm_record("id: 1", tail="\ntitle: body\n"),
                             "decisions/fm-open.md": "---\nid: D-3\ntitle: Never closed\n\nSome prose.\n"})


class RecordsStale(Tree):
    def published(self, extra=None):
        root = self.tree(with_records(extra))
        self.publish(root)
        self.assertEqual(generator(root, "--check"), (0, "", ""))
        return root

    def test_b1_a_new_debt_fails_the_check_until_the_page_is_written_again(self):
        root = self.published()
        put(root, "debts/new-gap.md", DEBT.replace("Gap one", "New gap"))
        code, out, err = generator(root, "--check")
        self.assertEqual(code, 1, out + err)
        self.assertIn("docs/records.md", out + err)
        self.assertIn("stale", (out + err).lower())
        self.publish(root)
        self.assertEqual(generator(root, "--check"), (0, "", ""))
        self.assertIn("new-gap", listed(records_rows(self.records_text(root)))["Debts"])

    def test_b2_every_kind_of_change_makes_the_page_stale(self):
        changes = {
            "a debt is added": lambda root: put(root, "debts/new-gap.md", DEBT),
            "a debt is deleted": lambda root: os.remove(os.path.join(root, "debts", "gap-one.md")),
            "a debt's What changes": lambda root: put(
                root, "debts/gap-one.md", DEBT.replace("The check misses one case.", "The check misses two cases.")),
            "a decision is added": lambda root: put(root, "decisions/new.md", LOOSE),
            "a decision gains a Kind line": lambda root: put(root, "decisions/loose.md", LOOSE + "\nKind: process\n"),
            "a plan is added": lambda root: put(root, "plans/new.md", PLAN),
            "a rule marker is added": lambda root: put(root, "CLAUDE.md", RULES + "\nShip it.<!-- rule:b-four -->\n"),
            "a rule marker is deleted": lambda root: put(root, "CLAUDE.md", RULES.replace("<!-- rule:b-three -->", "")),
        }
        for name, change in changes.items():
            with self.subTest(name):
                root = self.published()
                change(root)
                code, out, err = generator(root, "--check")
                self.assertEqual(code, 1, out + err)
                self.assertIn("docs/records.md", out + err)
                self.publish(root)
                self.assertEqual(generator(root, "--check"), (0, "", ""))

    def test_b3_a_hand_edit_of_the_page_is_stale(self):
        root = self.published()
        put(root, "docs/records.md", self.records_text(root) + "\nA hand-written line.\n")
        code, out, err = generator(root, "--check")
        self.assertEqual(code, 1, out + err)
        self.assertIn("docs/records.md", out + err)

    def test_b4_the_check_reads_both_pages(self):
        for rel in ("docs/catalog.md", "docs/records.md"):
            with self.subTest(rel):
                root = self.published()
                self.assertTrue(os.path.exists(os.path.join(root, *rel.split("/"))), "%s was not written" % rel)
                os.remove(os.path.join(root, *rel.split("/")))
                code, out, err = generator(root, "--check")
                self.assertEqual(code, 1, out + err)
                self.assertIn(rel, out + err)

    def test_b5_a_write_on_a_current_page_changes_nothing(self):
        root = self.published()
        before = self.records_text(root)
        self.publish(root)
        self.assertEqual(self.records_text(root), before)

    # Merge-time rebuild: the merge rewrites the page, so a pull request
    # run does not fail on a stale one. The stamp engine reads a pull request run from GITHUB_BASE_REF or a
    # GITHUB_REF under refs/pull/, and each alone counts.
    PULL_REQUEST_RUNS = ({"GITHUB_BASE_REF": "main"}, {"GITHUB_REF": "refs/pull/12/merge"},
                         {"GITHUB_BASE_REF": "main", "GITHUB_REF": "refs/pull/12/merge"})

    def test_b6_on_a_pull_request_a_stale_page_is_not_red(self):
        for pr_env in self.PULL_REQUEST_RUNS:
            with self.subTest(pr_env):
                root = self.published()
                put(root, "debts/new-gap.md", DEBT.replace("Gap one", "New gap"))
                self.assertEqual(generator(root, "--check", env=pr_env), (0, "", ""))

    def test_b7_on_a_pull_request_a_missing_records_page_is_not_red(self):
        for pr_env in self.PULL_REQUEST_RUNS:
            with self.subTest(pr_env):
                root = self.published()
                self.records_text(root)  # a failure, not an error, while the page is not written
                os.remove(os.path.join(root, "docs", "records.md"))
                self.assertEqual(generator(root, "--check", env=pr_env), (0, "", ""))

    def test_b8_on_a_push_to_the_default_branch_a_stale_page_is_red(self):
        # The signal that a merge made without the tool, or a failed rebuild, left main with a stale index.
        root = self.published()
        put(root, "debts/new-gap.md", DEBT.replace("Gap one", "New gap"))
        for push_env in ({"GITHUB_REF": "refs/heads/main"}, {"GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "push"}):
            with self.subTest(push_env):
                code, out, err = generator(root, "--check", env=push_env)
                self.assertEqual(code, 1, out + err)
                self.assertIn("docs/records.md", out + err)
        self.records_text(root)
        os.remove(os.path.join(root, "docs", "records.md"))
        code, out, err = generator(root, "--check", env={"GITHUB_REF": "refs/heads/main"})
        self.assertEqual(code, 1, out + err)
        self.assertIn("docs/records.md", out + err)

    def test_b9_a_problem_is_red_on_a_pull_request_too(self):
        # Only a stale page is waived. A history marker, an empty record or an unreadable file fails everywhere:
        # the merge refuses to write over a problem, so waiting for it would stop the merge late.
        root = self.published()
        put(root, "decisions/old.md", old_decision("Superseded: x."))
        put(root, "debts/empty.md", "\n")
        code, out, err = generator(root, "--check", env={"GITHUB_BASE_REF": "main"})
        self.assertEqual(code, 1, out + err)
        self.assertIn("decisions/old.md:7", out + err)
        self.assertIn("debts/empty.md", out + err)

    def test_b10_the_catalog_page_stays_strict_on_a_pull_request(self):
        # The pull request waiver covers the records page only.
        root = self.published()
        put(root, "hooks/ok.py", '"""Does another thing now."""\nprint("ok")\n')
        code, out, err = generator(root, "--check", env={"GITHUB_BASE_REF": "main"})
        self.assertEqual(code, 1, out + err)
        self.assertIn("docs/catalog.md", out + err)
        self.assertNotIn("docs/records.md", out + err)


NOT_HISTORY = [
    ("mid-sentence no longer", "# Old thing", "The guard no longer crashes when the key is missing."),
    ("superseded runs of a CI job", "# Old thing", "`concurrency` cancels superseded runs on pull requests only."),
    ("a PR closes as superseded", "# Old thing", "The old PR closes as superseded."),
    ("a heading that holds the phrase", "# Repeal: prose above the report no longer needs a question", "The repeal is plain."),
    ("a rule id in a comment", "# Old thing", "<!-- rule:speak-rewrite-superseded-in-place -->"),
    ("inline code opens the line", "# Old thing", "`Superseded` is a label this check refuses."),
    ("a wrapped continuation line", "# Old thing", "The guard stops the run when the\nno longer needed flag is set."),
    ("the rule's own words on a wrapped line", "# Old thing", "Rewrite\nsuperseded text in place. Keep only what is true now."),
    ("a fence", "# Old thing", "```\nSuperseded: x\nno longer\nOld ruling: y\n```"),
    ("a tilde fence", "# Old thing", "~~~\nPreviously: x\n~~~"),
    ("a fence of three inside a fence of four", "# Old thing", "````\n```\nPreviously: still inside the outer fence\n```\n````"),
    ("was: in inline code", "# Old thing", "The marker `was:` opens old text."),
    ("was: in a fence", "# Old thing", "```\nThe old wording was: x\n```"),
]

# Each body ends in a line that must fail, whatever text comes before it.
AFTER_TRAPS = [
    ("a fence with a comment opener and quotes", "```\n<!-- not closed\nit's \"quoted\n```\n\nSuperseded: caught after the fence."),
    ("a comment opener in inline code", "Write `<!--` to open a comment.\n\nPreviously: caught after the code span."),
    ("lone quotes in text", "The word \"ruling is open and it's not closed.\n\nOverruled: caught after the quotes."),
    ("a fence of four around a fence of three", "````\n```\ninner\n```\n````\n\nOld ruling: caught after the outer fence."),
    ("a tilde fence", "~~~\nx\n~~~\n\nSuperseded: caught after the tilde fence."),
]

HISTORY_LINES = [
    "## Superseded", "## Old ruling", "### Previously, the guard allowed it", "## Overruled on 2026-10-01",
    "## Was: allow it", "## No longer in force",
    "Superseded by the floor rule.", "Overruled on 2026-10-01 by the owner.", "Previously the guard allowed it.",
    "Old ruling: allow it.", "was: allow it.", "No longer in force: allow it.", "superseded by the floor rule.",
    "OLD RULING: allow it.",
    "- Superseded: allow it.", "* Overruled by the floor.", "1. Previously allowed.", "  - was: allow it.",
    "**Old ruling:** allow it.", "_Previously_ the guard allowed it.", "- **Superseded.** Allow it.",
    "The old wording was: allow it.", "Some text; the old rule was: allow it.",
]


class RecordsHistory(Tree):
    def assert_history(self, spec, where):
        code, out, err = generator(self.tree(spec), "--check")
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("Traceback", out + err)
        self.assertRegex(out + err, re.escape(where) + r"(?!\d)")

    def test_c1_a_marker_that_opens_a_heading_or_a_block_fails_with_file_and_line(self):
        for line in HISTORY_LINES:
            with self.subTest(line):
                self.assert_history(with_records({"decisions/old.md": old_decision(line)}), "decisions/old.md:7")

    def test_c2_every_record_folder_and_claude_md_is_read(self):
        cases = [
            ("plans/old.md", "# Plan\n\n## Old ruling\n\nText.\n", "## Old ruling"),
            ("debts/old.md", DEBT + "\nPreviously: the check ran.\n", "Previously: the check ran."),
            ("CLAUDE.md", RULES + "\nOverruled: the old rule text.\n", "Overruled: the old rule text."),
        ]
        for rel, text, line in cases:
            with self.subTest(rel):
                self.assert_history(with_records({rel: text}), "%s:%d" % (rel, line_of(text, line)))

    def test_c3_the_failure_names_every_offender(self):
        spec = with_records({"decisions/a.md": old_decision("Superseded: a."), "decisions/b.md": old_decision("Overruled: b.")})
        code, out, err = generator(self.tree(spec), "--check")
        self.assertEqual(code, 1, out + err)
        self.assertIn("decisions/a.md:7", out + err)
        self.assertIn("decisions/b.md:7", out + err)
        self.assertGreaterEqual(len([ln for ln in (out + err).splitlines() if ".md:" in ln]), 2, out + err)

    def test_c4_the_page_is_not_written_while_a_problem_stands(self):
        root = self.tree(with_records({"decisions/old.md": old_decision("Superseded: x.")}))
        code, out, err = generator(root)
        self.assertEqual(code, 1, out + err)
        self.assertIn("decisions/old.md:7", out + err)
        self.assertFalse(os.path.exists(os.path.join(root, "docs", "records.md")), "a page was written over a problem")

    def test_c5_prose_and_code_that_only_use_the_words_do_not_fail(self):
        # Each case also needs its record on the page, so a generator that is silent for all input fails here.
        for name, title, body in NOT_HISTORY:
            with self.subTest(name):
                root = self.tree(with_records({"decisions/old.md": old_decision(body, title)}))
                self.publish(root)
                self.assertEqual(generator(root, "--check"), (0, "", ""))
                self.assertIn("old", listed(records_rows(self.records_text(root)))["Unsorted decisions"])

    def test_c6_a_trap_before_the_marker_does_not_hide_it_or_its_line_number(self):
        for name, body in AFTER_TRAPS:
            with self.subTest(name):
                text = old_decision(body)
                last = body.split("\n")[-1]
                self.assert_history(with_records({"decisions/old.md": text}), "decisions/old.md:%d" % line_of(text, last))

    def test_c7_crlf_and_a_bom_do_not_move_the_line_number(self):
        text = "﻿" + old_decision("Previously: the guard allowed it.").replace("\n", "\r\n")
        self.assert_history(with_records({"decisions/old.md": text}), "decisions/old.md:7")

    def test_c10_was_colon_fails_on_a_wrapped_line_too(self):
        text = old_decision("The old rule text goes\nhere, and was: allow it.\nThen more.")
        self.assert_history(with_records({"decisions/old.md": text}),
                            "decisions/old.md:%d" % line_of(text, "here, and was: allow it."))

    def test_c11_history_hidden_in_a_comment_fails_when_it_opens_a_block(self):
        text = old_decision("<!--\n\nSuperseded: hidden old text.\n\n-->")
        self.assert_history(with_records({"decisions/old.md": text}),
                            "decisions/old.md:%d" % line_of(text, "Superseded: hidden old text."))

    def test_c8_a_debt_what_may_say_no_longer(self):
        cases = [
            ("opens its text", "- **What.** No longer checks X. The gap is real.\n", "No longer checks X."),
            ("wraps", "- **What.** The check is wrong when the file\n  no longer exists. A second sentence.\n",
             "The check is wrong when the file no longer exists."),
        ]
        for name, what, gist in cases:
            with self.subTest(name):
                debt = "# Gap\n\n%s- **Where.** `lint/x.py`.\n- **Decision.** none\n- **Retire.** Cover it.\n" % what
                root = self.tree(with_records({"debts/gap-one.md": debt}))
                self.publish(root)
                self.assertEqual(generator(root, "--check"), (0, "", ""))
                rows = records_rows(self.records_text(root))
                self.assertEqual({r["slug"]: r["gist"] for r in rows if r["section"] == "Debts"}["gap-one"], gist)

    def test_c9_the_wording_of_a_real_rule_passes_in_claude_md(self):
        claude = RULES + ("\n**Speak plainly.** Rewrite\nsuperseded text in place. Keep only what is true now."
                          "<!-- rule:speak-rewrite-superseded-in-place -->\n"
                          "Remove the file when the raise is no longer needed.<!-- rule:roles-remove-override-file -->\n")
        root = self.tree(with_records({"CLAUDE.md": claude}))
        self.publish(root)
        self.assertEqual(generator(root, "--check"), (0, "", ""))
        gists = {r["slug"]: r["gist"] for r in records_rows(self.records_text(root)) if r["section"] == "Mandates"}
        self.assertEqual(gists["speak-rewrite-superseded-in-place"], "Rewrite superseded text in place.")
        self.assertEqual(gists["roles-remove-override-file"], "Remove the file when the raise is no longer needed.")

    def test_c12_words_that_only_look_like_a_marker_do_not_fail(self):
        # None of the prose lines below is overruled text. The control line must still fail the check,
        # so a detector gone silent cannot pass this case.
        for line in ["The flag was: on.", "No longer used: the old flag.", "Previously-run tests stay green."]:
            with self.subTest(line):
                root = self.tree(with_records({"decisions/old.md": old_decision(line)}))
                self.publish(root)
                self.assertEqual(generator(root, "--check"), (0, "", ""))
                self.assertIn("old", listed(records_rows(self.records_text(root)))["Unsorted decisions"])
        self.assert_history(with_records({"decisions/old.md": old_decision("Old ruling: allow it.")}), "decisions/old.md:7")

    def test_c13_only_in_force_opens_a_no_longer_marker(self):
        # "No longer" marks overruled text only as "No longer in force". The first three lines are not
        # markers. The fourth is a bare "No longer".
        for line in ["No longer holds: the rule.", "No longer applies: the flag.", "No longer valid: the flag.", "No longer checks the flag."]:
            with self.subTest(line):
                root = self.tree(with_records({"decisions/old.md": old_decision(line)}))
                self.publish(root)
                self.assertEqual(generator(root, "--check"), (0, "", ""))
                self.assertIn("old", listed(records_rows(self.records_text(root)))["Unsorted decisions"])
        self.assert_history(with_records({"decisions/old.md": old_decision("No longer in force: the flag.")}), "decisions/old.md:7")

    def test_c14_limit_old_before_was_colon_flags_as_pinned(self):
        # NAMED LIMIT, pinned as the current behaviour. The "old" rule flags "was:" when "old" comes earlier in the same
        # block, so it cannot tell a description from overruled text. Contrast c12: "The flag was: on." has no "old" and
        # passes. Debt: a record in the debt store is still owed (debts/ is not a test path). A change here is a rule change.
        self.assert_history(with_records({"decisions/old.md": old_decision("The old flag was: on.")}), "decisions/old.md:7")


class OtherRepos(Tree):
    """A repo that is not this one: no hooks, mods or skills, so no catalog. It runs the same generator."""

    def write(self, root, elsewhere, *args):
        return generator(root, *args, cwd=elsewhere, flag_root=True)

    def test_d1_a_repo_with_only_decisions_and_debts_gets_only_its_records_page(self):
        root, elsewhere = self.tree(lean()), self.tree({})
        code, out, err = self.write(root, elsewhere)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("settings.json", out + err)
        self.assertNotIn("cannot read", out + err)
        path = os.path.join(root, "docs", "records.md")
        self.assertTrue(os.path.exists(path), "docs/records.md was not written")
        self.assertFalse(os.path.exists(os.path.join(root, "docs", "catalog.md")), "a catalog was written for a repo with no catalog part")
        self.assertEqual(os.listdir(elsewhere), [], "the root came from the working folder, not from --root")
        page = read(path)
        self.assertEqual([h for h in re.findall(r"^## (.+?)\s*$", page, re.M) if h in SECTIONS],
                         ["Rulings", "Build designs", "Unsorted decisions", "Debts"])
        self.assertEqual(listed(records_rows(page)), {
            "Rulings": ["ruled"], "Build designs": ["built"], "Unsorted decisions": ["loose"], "Debts": ["gap-one"]})

    def test_d2_the_check_needs_no_catalog_and_goes_red_on_a_stale_page(self):
        root, elsewhere = self.tree(lean()), self.tree({})
        code, out, err = self.write(root, elsewhere)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.write(root, elsewhere, "--check"), (0, "", ""))
        put(root, "debts/new-gap.md", DEBT.replace("Gap one", "New gap"))
        code, out, err = self.write(root, elsewhere, "--check")
        self.assertEqual(code, 1, out + err)
        self.assertIn("docs/records.md", out + err)

    def test_d3_the_environment_variable_and_the_flag_write_the_same_page(self):
        by_env, by_flag, elsewhere = self.tree(lean()), self.tree(lean()), self.tree({})
        self.publish(by_env)
        code, out, err = self.write(by_flag, elsewhere)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.records_text(by_env), self.records_text(by_flag))

    def test_d4_a_repo_with_a_catalog_part_and_no_settings_json_is_still_exit_2(self):
        spec = lean({"hooks/ok.py": '"""Does one thing."""\n'})
        code, out, err = generator(self.tree(spec))
        self.assertEqual(code, 2, out + err)
        self.assertIn("settings.json", out + err)


    def test_d5_a_repo_with_no_records_gets_no_page(self):
        # The merge tool runs the generator on every repo it merges, so a repo with no records must stay as it is.
        for name, spec in (("nothing", {"README.md": "# A repo\n"}), ("only a folder readme", {"debts/README.md": "# Debts\n"})):
            with self.subTest(name):
                root, elsewhere = self.tree(spec), self.tree({})
                before = sorted(os.listdir(root))
                code, out, err = self.write(root, elsewhere)
                self.assertEqual(code, 0, out + err)
                self.assertEqual(sorted(os.listdir(root)), before, "a page was written for a repo with no records")
                self.assertEqual(self.write(root, elsewhere, "--check"), (0, "", ""))


@unittest.skipIf(pull_request_run(), "the merge rebuilds the records page, so a pull request need not carry a fresh one")
class RealRecords(unittest.TestCase):
    """The committed page against the real records. Skipped on a pull request run (the merge rebuilds the
    page); run on a laptop and on a push to main."""

    def rows(self):
        if not os.path.exists(RECORDS_PAGE):
            self.fail("docs/records.md does not exist yet: the generator writes it")
        return records_rows(read(RECORDS_PAGE))

    def test_r10_every_record_file_has_one_row_and_a_link_that_resolves(self):
        rows = self.rows()
        folders = (("docs/decisions", ("Rulings", "Build designs", "Unsorted decisions")), ("docs/debts", ("Debts",)),
                   ("docs/plans", ("Plans",)))
        problems = []
        for folder, sections in folders:
            # docs/debts/notes.md is the notes tier, no record: a row for it is an extra.
            # Compared by path: a docs/decisions/notes.md is still a record and needs its row.
            names = sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, *folder.split("/")))
                           if f.endswith(".md") and f != "README.md" and "%s/%s" % (folder, f) != "docs/debts/notes.md")
            self.assertTrue(names, "no record in %s, so the scan proves nothing" % folder)
            got = sorted(r["slug"] for r in rows if r["section"] in sections)
            if got != names:
                problems.append("%s: missing %s, extra or twice %s" % (
                    folder, sorted(set(names) - set(got)), sorted(s for s in set(got) if got.count(s) > 1 or s not in names)))
        for r in rows:
            target = os.path.normpath(os.path.join(ROOT, "docs", *r["link"].split("/"))) if r["link"] else ""
            if not target or not os.path.isfile(target):
                problems.append("%s %s: link %r does not resolve" % (r["section"], r["slug"], r["link"]))
        self.assertFalse(problems, "\n".join(problems))

    def test_r11_every_rule_marker_in_claude_md_has_one_mandate_row_in_order(self):
        ids = []
        for line in unfenced_lines(read(os.path.join(ROOT, "CLAUDE.md"))):
            ids += [i for i in RULE_MARK.findall(line) if i not in ids]
        self.assertTrue(ids, "no rule marker in CLAUDE.md, so the scan proves nothing")
        self.assertEqual([r["slug"] for r in self.rows() if r["section"] == "Mandates"], ids)

    def test_r12_every_gist_is_filled_in(self):
        problems = []
        for r in self.rows():
            # Markdown noise: a heading, table or quote mark, a list marker, or (a mandate) its bold lead label.
            noise = re.match(r"(#|\||>|[-*+]\s)", r["gist"]) or (r["section"] == "Mandates" and r["gist"].startswith("**"))
            if not r["gist"].strip() or noise:
                problems.append("%s %s: gist %r" % (r["section"], r["slug"], r["gist"]))
        self.assertFalse(problems, "\n".join(problems))

    def test_r13_the_real_kind_lines_decide_the_group(self):
        # A record may fence an example of both kinds (the FENCED_KINDS fixture); only its unfenced Kind lines decide the group.
        got = {r["slug"]: r["section"] for r in self.rows() if r["section"] in ("Rulings", "Build designs", "Unsorted decisions")}
        problems = []
        for name in sorted(os.listdir(os.path.join(ROOT, "docs", "decisions"))):
            if not name.endswith(".md"):
                continue
            kinds = {m.group(1) for m in map(KIND_LINE.match, unfenced_lines(read(os.path.join(ROOT, "docs", "decisions", name)))) if m}
            want = {frozenset(["process"]): "Rulings", frozenset(["build"]): "Build designs", frozenset(): "Unsorted decisions"}.get(frozenset(kinds))
            if want and got.get(name[:-3]) != want:
                problems.append("%s: listed under %r, want %r" % (name, got.get(name[:-3]), want))
        self.assertIn("rulings-declare-kind", got, "rulings-declare-kind is not listed")
        self.assertFalse(problems, "\n".join(problems))


class Helpers(unittest.TestCase):
    def test_u1_escaped_pipe_in_a_code_span_stays_in_its_cell(self):
        self.assertEqual(split_cells("| `Bash\\|PowerShell` | x |"), ["`Bash|PowerShell`", "x"])

    def test_u5_records_rows_reads_each_section_and_unescapes_a_pipe(self):
        text = ("# Records\n\n## Debts\n\n| Slug | Gist | Link |\n|---|---|---|\n"
                "| `a-b` | One \\| two. | [a-b](../debts/a-b.md) |\n\n"
                "## Plans\n\n| Slug | Gist | Link |\n|---|---|---|\n| `p` | Plan. | [p](../plans/p.md) |\n")
        self.assertEqual(records_rows(text), [
            {"section": "Debts", "slug": "a-b", "gist": "One | two.", "link": "../debts/a-b.md"},
            {"section": "Plans", "slug": "p", "gist": "Plan.", "link": "../plans/p.md"}])

    def test_u6_unfenced_lines_closes_a_fence_only_on_its_own_kind(self):
        text = "a\n````\n```\nb\n```\n````\nc\n~~~\nd\n~~~\ne\n```text\nf\n```\n"
        self.assertEqual(list(unfenced_lines(text)), ["a", "c", "e", ""])

    def test_u7_line_of_counts_from_one(self):
        self.assertEqual(line_of("a\n\nb\nb\n", "b"), 3)

    def test_the_guards_records_header_opens_the_generated_intro(self):
        """hooks/guard_merge.py copies the first line of RECORDS_INTRO as RECORDS_HEADER. If the intro title changes
        and the copy does not, the guard stops matching the page and lets each lane commit of it pass."""
        hooks = os.path.join(ROOT, "hooks")
        sys.path.insert(0, hooks)
        try:
            from guard_merge import RECORDS_HEADER
        finally:
            sys.path.remove(hooks)
        from hook_catalog import RECORDS_INTRO
        self.assertTrue(RECORDS_HEADER.strip(), "RECORDS_HEADER is empty")
        self.assertTrue(RECORDS_INTRO.startswith(RECORDS_HEADER), (RECORDS_HEADER, RECORDS_INTRO[:40]))


# ---- the cell cap: a long description cell is cut and ends in an ellipsis ---------------------
# Decision catalog-cells-never-cut: the cap sits above the longest current cell, so no cell loses text.
# A cap stays only as a ceiling for growth. Sources (SKILL.md, plugin.json, the judge prompts in settings.json)
# are never edited. The cap is one named constant in lint/hook_catalog.py, CELL_CAP. The cases import it,
# so a new value moves every case with it. No case copies the number.

ELLIPSIS = "…"
PROSE = "alpha beta gamma delta "
JUDGE_KEY = "Judge this AskUserQuestion call: $ARGUMENTS"


def cell_cap():
    """CELL_CAP from the generator. A missing name fails the case by its name."""
    try:
        from hook_catalog import CELL_CAP
    except ImportError as err:
        raise AssertionError("lint/hook_catalog.py has no CELL_CAP, the one named cap on a description cell: %s" % err)
    return CELL_CAP


def prose(n):
    """Plain prose of exactly n characters that ends in a letter, so flattening it keeps its length."""
    text = (PROSE * (n // len(PROSE) + 2))[:n]
    return text[:-1] + "e" if text.endswith(" ") else text


def filler(n):
    """A judge body of at least n characters."""
    sentence = "Check each question and option against the brief it cites. "
    return sentence * (n // len(sentence) + 1)


def what_of(out, key):
    """The What it does cell of the row keyed key in a rendered page, pipes unescaped."""
    return row_for(page_rows(out), key)["What it does"]


class CellCap(Tree):
    """A description cell longer than CELL_CAP is cut to at most CELL_CAP characters and ends in an ellipsis.
    The cut keeps the start of the source, never splits a backtick span, and leaves every row its cells."""

    def render(self, tree_files):
        code, out, err = generator(self.tree(tree_files), "--print")
        self.assertEqual(code, 0, out + err)
        return out

    def render_skill(self, text):
        return self.render(files(extra={"skills/alpha/SKILL.md": skill_md("description: " + text)}))

    def assert_cut(self, cell, source, floor=True):
        """The cell ends in the ellipsis, keeps the start of the source, and fits the cap. floor=False when the
        cut must fall before a span longer than the cap, so the cell may be short."""
        self.assertTrue(cell.endswith(ELLIPSIS), "not cut: %d chars, and no ellipsis at the end" % len(cell))
        self.assertTrue(" ".join(source.split()).startswith(cell[:-1]), "the cut rewords the source: %r" % cell)
        cap = cell_cap()
        self.assertLessEqual(len(cell), cap, "%d chars, over the cap of %d" % (len(cell), cap))
        if floor:
            self.assertGreater(len(cell), cap // 2, "the cut keeps too little: %d chars at a cap of %d" % (len(cell), cap))

    def assert_span_cut(self, out, key, source, floor=True):
        """A cut that would split a backtick span falls before the span: the cell has no backtick, and the row keeps its cells."""
        cell = what_of(out, key)
        self.assert_cut(cell, source, floor)
        self.assertNotIn("`", cell, "the cut keeps or opens a backtick span: %r" % cell[-30:])
        rows = [line for line in out.split("\n") if line.startswith("| `%s`" % key)]
        self.assertEqual(len(rows), 1, out)
        self.assertEqual(len(split_cells(rows[0])), len(COLUMNS), "the cut leaves an unbalanced pipe: " + rows[0])

    def test_e1_the_cap_is_one_named_positive_integer_in_the_generator(self):
        cap = cell_cap()
        self.assertIsInstance(cap, int)
        self.assertGreater(cap, 0)

    def test_e2_a_skill_description_over_the_cap_is_cut_and_ends_in_an_ellipsis(self):
        text = prose(2 * cell_cap())
        self.assert_cut(what_of(self.render_skill(text), "skills/alpha"), text)

    def test_e3_a_mod_description_over_the_cap_is_cut(self):
        text = prose(2 * cell_cap())
        out = self.render(files(plugins={"tw@claude-settings": True}, extra={
            "mods/tw/.claude-plugin/plugin.json": json.dumps({"description": text}),
            "mods/tw/SOURCE.md": "repo and commit go here\n",
        }))
        self.assert_cut(what_of(out, "mods/tw"), text)

    def test_e4_a_judge_prompt_over_the_cap_is_cut(self):
        body = filler(2 * cell_cap())
        prompt = JUDGE_KEY + "\n" + body + "Block only on a clear breach of the brief."
        out = self.render(files(hooks={"PreToolUse": [{"matcher": "AskUserQuestion", "hooks": [judge(prompt=prompt)]}]}))
        self.assert_cut(what_of(out, JUDGE_KEY), body)

    def test_e5_a_short_description_renders_unchanged(self):
        # Pins that a cell under the cap is never touched.
        self.assertEqual(what_of(self.render(files()), "skills/alpha"), "Use when testing alpha.")

    def test_e6_a_description_of_exactly_the_cap_is_unchanged_and_one_more_character_is_cut(self):
        cap = cell_cap()
        self.assertEqual(what_of(self.render_skill(prose(cap)), "skills/alpha"), prose(cap))
        cell = what_of(self.render_skill(prose(cap + 1)), "skills/alpha")
        self.assertTrue(cell.endswith(ELLIPSIS), "%d chars at the cap plus one: no ellipsis" % len(cell))
        self.assertLessEqual(len(cell), cap)

    def test_e7_a_span_longer_than_the_cap_is_cut_before_it(self):
        cap = cell_cap()
        text = "ab `x " + "c" * cap + " | " + "d" * 60 + "` " + PROSE * 20  # the span runs past the cap, with a space inside before it
        self.assert_span_cut(self.render_skill(text), "skills/alpha", text, floor=False)

    def test_e12_a_short_span_that_straddles_the_cap_is_cut_before_it(self):
        cap = cell_cap()
        text = prose(cap - 40) + " `" + "c" * 10 + " | " + "d" * 60 + "` " + PROSE * 20  # starts before the cap, ends after, with spaces inside before it
        self.assert_span_cut(self.render_skill(text), "skills/alpha", text)

    def test_e9_comment_openers_inside_a_code_span_at_the_cut_are_text_not_comments(self):
        # Scanner rule (building-scanner-respects-strings): #, // and /* inside a code span are text.
        cap = cell_cap()
        text = prose(cap - 25) + " `" + "x" * 10 + " // # /* opener " + "y" * 60 + "` " + PROSE * 20  # openers at the cap
        out = self.render(files(extra={"skills/alpha/SKILL.md": skill_md('description: "%s"' % text)}))
        self.assert_span_cut(out, "skills/alpha", text)

    def test_e10_a_lone_backtick_in_plain_text_does_not_stop_the_cut(self):
        cap = cell_cap()
        text = "Use when a lone ` sits early in plain text, then " + prose(cap * 3)
        cell = what_of(self.render_skill(text), "skills/alpha")
        self.assert_cut(cell, text)
        self.assertIn("a lone ` sits early", cell)

    def test_e11_a_code_span_that_a_folded_line_break_splits_is_one_span(self):
        # Scanner rule, the multi-line case: a folded frontmatter joins its two lines, so the span is one span.
        cap = cell_cap()
        lead = prose(cap - 100)
        folded = "description: >\n  " + lead + " `" + "c" * 60 + "\n  " + "d" * 60 + "` " + PROSE * 20
        source = lead + " `" + "c" * 60 + " " + "d" * 60 + "` " + PROSE * 20
        out = self.render(files(extra={"skills/alpha/SKILL.md": skill_md(folded)}))
        self.assert_span_cut(out, "skills/alpha", source)


class RealCellCap(unittest.TestCase):
    def test_e8_every_description_cell_of_the_committed_page_is_at_or_under_the_cap(self):
        if not os.path.exists(PAGE):
            self.fail("docs/catalog.md does not exist yet: the generator writes it")
        rows = page_rows(read(PAGE))
        self.assertTrue(rows, "no catalog rows, so the scan proves nothing")
        cap = cell_cap()
        over = ["%s %d chars" % (r["Key"], len(r["What it does"])) for r in rows if len(r["What it does"]) > cap]
        self.assertFalse(over, "over the cap of %d: %s" % (cap, "; ".join(over)))

    def test_e13_no_real_description_cell_is_cut(self):
        # Decision catalog-cells-never-cut: no cell loses text. Render the real repo at the cap and with
        # no cap; a row that differs was cut. The lists are zipped, never keyed: two judge rows share a key.
        import hook_catalog as gen
        saved = gen.CELL_CAP, gen.ROOT
        try:
            gen.ROOT = ROOT
            capped, problems = gen.render()
            gen.CELL_CAP = sys.maxsize
            full, more = gen.render()
        finally:
            gen.CELL_CAP, gen.ROOT = saved
        self.assertEqual(problems + more, [], "the real repo does not render")
        capped, full = page_rows(capped), page_rows(full)
        self.assertEqual(len(capped), len(full))
        self.assertTrue(full, "no catalog rows, so the scan proves nothing")
        cut = [(len(u["What it does"]), u["Key"]) for c, u in zip(capped, full) if c["What it does"] != u["What it does"]]
        self.assertFalse(cut, "%d cells cut at the cap of %d; the longest cell is %d chars, so the cap must be at least that: %s" % (
            len(cut), saved[0], max(len(u["What it does"]) for u in full), "; ".join("%s %d chars" % (k, n) for n, k in sorted(cut, reverse=True))))


if __name__ == "__main__":
    unittest.main()
