#!/usr/bin/env python3
"""Writes docs/catalog.md and docs/records.md. The catalog says what each hook, judge, mod and skill does.
The records page lists the records of a repo: its rules, decisions, debts and plans.

Plain words, one row each, and the model and
effort beside it, like the model table in the decision agent-model-cap. The page is
generated and never edited by hand. Each description comes from the source it describes, so
the page cannot drift from it.

    python3 lint/hook_catalog.py            write every page the root owns
    python3 lint/hook_catalog.py --print    write the catalog page to stdout, exit 1 while a problem stands
    python3 lint/hook_catalog.py --check    exit 0 and print nothing when each page is current
    python3 lint/hook_catalog.py --records-only   write docs/records.md alone (with --check, check it alone); the merge tool runs this

The root is `--root DIR`, else the folder in the environment variable HOOK_CATALOG_ROOT, else the repo
this script is in. It is never the working folder.

The catalog needs a hooks/, skills/ or mods/ folder. A root with none gets no catalog and is never asked
for settings.json. The records page is read from CLAUDE.md (the `<!-- rule:<id> -->` markers) and the .md
files in the record folders that lint/layout.json lists. A root with no record gets no records page. A record
that holds overruled text (a line that opens with Superseded, Overruled, Previously, No longer in force,
Old ruling or "was:", or a "was:" after the word "old" in its block) is a problem, and so is an empty one. No page is written while a problem stands.
The merge tool (merge/merge.py) writes the records page on the pull request head before it merges. So
`--check` waives a stale or missing records page on a pull request run (GITHUB_BASE_REF set, or GITHUB_REF
under refs/pull/), and fails on any other run.

Sources, all read from the root:
  settings.json `hooks`   one row per registration (event, matcher, `if`, command or prompt).
  a command's script      the first paragraph of a .py docstring, or the leading comment block
                          of a .sh script, after an optional shebang. A script that settings.json
                          runs in more than one way has a "Modes:" paragraph: one "- <key>: <text>"
                          line per mode, keyed by the flag the command passes after "$g", or by the
                          event when it passes none. The row takes the line for its flag, else for
                          its event. With no "Modes:" paragraph the row takes the first paragraph,
                          but only when every registration of the script has the same flag or
                          event. A "Modes:" paragraph with no line for a registration is a problem.
  an inline command       a command that names no script has no docstring. Its text is the
                          value in lint/hook_catalog_inline.json under its key: the registration
                          label (event, then " matcher=<m>" and " if=<c>" when set), then " #" and
                          the first 8 hex digits of the SHA-256 of the command text. A changed
                          command fails the check until its summary is reviewed and re-keyed.
  a prompt hook           the key is its first sentence. The text is the rest of the prompt,
                          up to the clause that blocks only on a clear breach.
  enabled repo mods       `enabledPlugins` keys `<name>@claude-settings` set true. The text is
                          the intro under the first heading of mods/<name>/README.md. A mod with no
                          README takes the `description` in its .claude-plugin/plugin.json,
                          and must hold a SOURCE.md (repo, commit, licence), which the page omits.
  skills                  the `description` in the frontmatter of skills/<name>/SKILL.md.
  model and effort        the row of the model table whose first cell names the script.

Exits 1 and prints one line per problem when a source is missing or empty, or the page is
stale. Exits 2 and names the path when an input cannot be read. Writing the page refuses to
run while a problem stands.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_skill_model_rows import skill_names  # noqa: E402  one home for "a skill is a folder with SKILL.md"
import layout  # noqa: E402  the one home of where records live (lint/layout.json)

ROOT = os.path.abspath(os.environ.get("HOOK_CATALOG_ROOT") or os.path.dirname(HERE))
PAGE = "docs/catalog.md"
TABLE_NAME = "agent-model-cap.md"  # the model table, a decision record
INLINE = "lint/hook_catalog_inline.json"
REGEN = "python3 lint/hook_catalog.py"
CELL_CAP = 1000  # ceiling on a description cell, in characters, the ellipsis included. It sits above the longest cell, so none is cut (decision catalog-cells-never-cut).
COLUMNS = ["Key", "Kind", "Event", "Matcher", "If", "Model", "Effort", "What it does"]
CMD_PATH = re.compile(r"\$\{CLAUDE_CONFIG_DIR:-\$HOME/\.claude\}/([\w./-]+\.(?:py|sh|mjs|js))")
CMD_FLAG = re.compile(r'"\$g"[ \t]+(--[\w-]+)')
MODE_LINE = re.compile(r"-\s+(\S+?):\s+(.*)$")
TABLE_PATH = re.compile(r"`([\w./-]+\.(?:py|sh|mjs|js))`")
BLOCK_CLAUSE = "Block only on a clear breach"
NO_MODEL = ("no model", "n/a")


class Unreadable(Exception):
    """An input the generator needs cannot be read. The message is its path."""


def read(rel):
    """Text of a file under the root, BOM and CRLF removed."""
    try:
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8-sig") as handle:
            return handle.read().replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as err:
        raise Unreadable(rel) from err


def has_file(rel):
    return os.path.isfile(os.path.join(ROOT, *rel.split("/")))


def flat(text):
    return " ".join(text.split())


def cell(text, cap=None):
    """One table cell: one line, a pipe written \\|, and <tag> text in a code span so a viewer shows it.
    With cap, a cell over cap characters is cut at a word and ends in an ellipsis, never inside a code span."""
    parts = re.split(r"(`[^`]*`)", flat(text))
    text = "".join(p if p.startswith("`") else re.sub(r"<[^<>\s][^<>]*>", r"`\g<0>`", p) for p in parts)
    if cap and len(text) > cap:
        end = max(text.rfind(" ", 0, cap), 0) or cap - 1
        for span in re.finditer(r"`[^`]*`", text):
            if span.start() < end < span.end():
                end = span.start()
        text = text[:end].rstrip() + "\u2026"
    return text.replace("|", "\\|")


def first_sentence(prompt):
    """Text up to and including the first '. ', or up to the first newline, whichever is first."""
    text = prompt.strip()
    cuts = [i for i in (text.find("\n"), text.find(". ")) if i != -1]
    end = min(cuts) if cuts else len(text)
    if end < len(text) and text[end] == ".":
        end += 1
    return text[:end].strip()


def split_cells(line):
    """Cells of one markdown table line. An escaped pipe stays inside its cell."""
    text = line.strip()
    body = text[1:-1] if text.endswith("|") else text[1:]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", body)]


# ---- readers: each returns the text a row shows, or "" when the source has none ----------------


def py_doc(text):
    """(first paragraph, modes) of the module docstring. Parsed with ast, never scanned.
    modes is None with no "Modes:" paragraph, else {flag or event: text}."""
    paras = (ast.get_docstring(ast.parse(text)) or "").strip().split("\n\n")
    for para in paras:
        lines = para.strip().split("\n")
        if lines[0].strip() != "Modes:":
            continue
        modes, key = {}, None
        for line in lines[1:]:
            found = MODE_LINE.match(line.strip())
            if found:
                key = found.group(1)
                modes[key] = found.group(2)
            elif key:
                modes[key] += " " + line.strip()
        return flat(paras[0]), {k: flat(v) for k, v in modes.items()}
    return flat(paras[0]), None


def sh_doc(text):
    """The comment block at the top of a shell script, after an optional shebang. It stops at
    the first line that does not start with #, so a # inside a string or a here-document later
    in the script never counts."""
    lines = text.split("\n")
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    block = []
    for line in lines:
        if not line.startswith("#"):
            break
        block.append(line.lstrip("#"))
    return flat(" ".join(block))


def frontmatter_description(text):
    """The `description` value of a SKILL.md frontmatter: plain, quoted, or a > or | block."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return ""
    front = []
    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        front.append(line)
    else:
        return ""  # never closed: no frontmatter
    for i, line in enumerate(front):
        found = re.match(r"description:[ \t]*(.*)$", line)
        if not found:
            continue
        rest = []
        for more in front[i + 1:]:
            if more.strip() and not more[:1].isspace():
                break
            rest.append(more.strip())
        first = found.group(1).strip()
        joined = flat(" ".join([first] + rest))
        if re.match(r"[>|][+-]?\d?\s*(#.*)?$", first):
            return flat(" ".join(rest))
        if first[:1] in ('"', "'"):
            return unquote(joined)
        return re.sub(r"(?:^|\s+)#.*$", "", joined).strip()  # a plain value ends at " #"
    return ""


def unquote(text):
    """The YAML quoted scalar that starts text. A closing quote ends it."""
    quote, out, i = text[0], [], 1
    while i < len(text):
        ch = text[i]
        if quote == '"' and ch == "\\" and i + 1 < len(text):
            out.append(text[i + 1] if text[i + 1] in '"\\' else ch + text[i + 1])
            i += 2
            continue
        if quote == "'" and text[i:i + 2] == "''":
            out.append("'")
            i += 2
            continue
        if ch == quote:
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def under_first_heading(text):
    """The text under the first heading, up to the next heading, with list markers dropped.
    A line inside a fenced block is never a heading."""
    out, seen, fence = [], False, False
    for line in text.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        elif not fence and re.match(r"#{1,6}\s", line):
            if seen:
                break
            seen = True
            continue
        if seen:
            out.append(re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line))
    return flat(" ".join(out))


def mod_manifest_description(base):
    """The `description` in a mod's .claude-plugin/plugin.json, or "" when it has none."""
    rel = base + "/.claude-plugin/plugin.json"
    if not has_file(rel):
        return ""
    try:
        return flat(str(json.loads(read(rel)).get("description") or ""))
    except ValueError as err:
        raise Unreadable(rel) from err


def judge_text(prompt, key):
    """The prompt after its first sentence, up to the standard block-on-breach clause."""
    rest = prompt.strip()[len(key):]
    rest = rest.split(BLOCK_CLAUSE)[0]
    return flat(rest) or key


def calls_invoke_model(text):
    """True when the script defines or calls invoke_model."""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == "invoke_model":
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if (func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")) == "invoke_model":
                return True
    return False


# ---- inputs ------------------------------------------------------------------------------------


def load_settings():
    try:
        return json.loads(read("settings.json"))
    except ValueError as err:
        raise Unreadable("settings.json") from err


def registrations(settings):
    """(event, matcher, if, hook) for each settings.json hook. An absent matcher or if is '-'."""
    for event, entries in settings.get("hooks", {}).items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                yield event, entry.get("matcher", "-"), hook.get("if", "-"), hook


def inline_summaries():
    """({inline_key: one-line summary}, [keys written twice]) for the commands that name no script.
    json.loads keeps the last of two equal keys without a word, so the pairs are read one by one."""
    if not has_file(INLINE):
        return {}, []  # no inline command needs it: a command that has none reports its own problem
    twice = []

    def pairs(items):
        keys = [k for k, _ in items]
        twice.extend(k for i, k in enumerate(keys) if k in keys[:i])
        return dict(items)
    try:
        found = json.loads(read(INLINE), object_pairs_hook=pairs)
    except ValueError as err:
        raise Unreadable(INLINE) from err
    if not isinstance(found, dict):
        raise Unreadable(INLINE)
    return found, twice


def model_table():
    """{script path: (model, effort)} for each model-table row that names a script."""
    found = {}
    for line in read(layout.path(ROOT, "decisions") + "/" + TABLE_NAME).split("\n"):
        if not line.lstrip().startswith("|"):
            continue
        cells = split_cells(line)
        path = TABLE_PATH.search(cells[0]) if cells else None
        if not path or len(cells) < 3:
            continue
        model = re.match(r"[\w.-]+", cells[1])
        found[path.group(1)] = (model.group(0) if model else "unknown", cells[2].strip("` ") or "unknown")
    return found


# ---- the page ----------------------------------------------------------------------------------

INTRO = """# Hook, judge, mod and skill catalog

This page says what each hook, judge, mod and skill in this repo does. A script writes it. Do not edit it by hand.

Run `%(regen)s` to write the page again. CI runs `%(regen)s --check`. The check fails when the page is stale or a source text is empty.

Where each text comes from:

- A hook runs a script. Its text is the first paragraph of the script docstring, or the leading comment block of a shell script. A script that runs under more than one flag or event needs a `Modes:` paragraph in its docstring. Each row takes the line for its flag or its event. A hook whose command is inline shell has no script, so its text is one line in `lint/hook_catalog_inline.json`. The key is the event and matcher, then a short hash of the command. A changed command fails the check until a person reviews its summary.
- A judge is a prompt hook that a model answers. Its key is the first sentence of the prompt. Its text is the rest of the prompt, up to the standard clause that blocks only on a clear breach.
- A mod is an enabled mod from this repo. Its text is the intro of its `README.md`. A mod with no README takes the `description` in its `plugin.json`, and must hold a `SOURCE.md`, which says where it came from. The page omits that file's text.
- A skill is a folder under `skills/`. Its text is the `description` in its `SKILL.md` frontmatter.

Model and effort come from the model table (decision `agent-model-cap`, the model per role). A hook with no row in that table calls no model, so its row says "no model". A judge takes the `model` field of its prompt hook, and a prompt hook has no effort field. A skill has no model pin, so its row says "no model" and effort "none". The model table has no row for a mod, so a mod row says "not listed". A mod may still call a model.

"""


def key_cell(text):
    return cell(text) if "`" in text else "`%s`" % cell(text)


def table(title, rows):
    out = ["## " + title, "", "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out) + "\n\n"


def label_of(event, matcher, cond):
    return event + ("" if matcher == "-" else " matcher=" + matcher) + ("" if cond == "-" else " if=" + cond)


def mode_key(event, command):
    """The mode a registration runs: the flag the command passes after "$g", else the event."""
    flag = CMD_FLAG.search(command)
    return flag.group(1) if flag else event


def inline_key(label, command):
    """The sidecar key of an inline command: its label, then " #" and a short hash of its text."""
    return "%s #%s" % (label, hashlib.sha256(command.encode("utf-8")).hexdigest()[:8])


def render():
    """(page text, problems). A problem is one line that names its offender."""
    settings = load_settings()
    models = model_table()
    inline, twice = inline_summaries()
    used = set()
    problems, hook_rows, docs = ["%s writes the key %r more than once" % (INLINE, k) for k in twice], [], {}

    def script_doc(path, label):
        """(first paragraph, modes) of a script, or ("", None) after a problem. Read once per path."""
        if path not in docs:
            text = read(path)
            ext = path.rsplit(".", 1)[1]
            docs[path] = ("", None)
            try:
                found = py_doc(text) if ext == "py" else (sh_doc(text), None) if ext == "sh" else None
            except SyntaxError as err:
                problems.append("%s: cannot parse %s (%s)" % (label, path, err.msg))
                return docs[path]
            if found is None:
                problems.append("%s: %s is a .%s file, and only .py and .sh have a docstring reader" % (label, path, ext))
            elif not found[0]:
                problems.append("%s: %s has no docstring (a .py docstring, or a .sh comment block after the shebang)" % (label, path))
            else:
                docs[path] = found
                if ext == "py" and path not in models and calls_invoke_model(text):
                    problems.append("%s: %s calls invoke_model but has no model-table row" % (label, path))
        return docs[path]

    modes_of = {}
    for event, _matcher, _cond, hook in registrations(settings):
        found = CMD_PATH.search(hook.get("command", "")) if hook.get("type") == "command" else None
        if found:
            modes_of.setdefault(found.group(1), set()).add(mode_key(event, hook["command"]))

    def script_row(path, label, event, command):
        """The text of a script row: its mode line when the docstring has modes, else the first paragraph."""
        first, modes = script_doc(path, label)
        if not first:
            return first
        mode = mode_key(event, command)
        if modes is None:
            if len(modes_of[path]) == 1:
                return first
            problems.append("%s: %s runs as %s, so its docstring needs a Modes: paragraph with one line each"
                            % (label, path, ", ".join(sorted(modes_of[path]))))
            return ""
        if mode not in modes:
            problems.append("%s: %s has a Modes: paragraph with no line for %s" % (label, path, mode))
            return ""
        return modes[mode]

    for event, matcher, cond, hook in registrations(settings):
        label = label_of(event, matcher, cond)
        kind = hook.get("type")
        if kind == "command":
            found = CMD_PATH.search(hook.get("command", ""))
            if not found:
                key = inline_key(label, hook.get("command", ""))
                text = inline.get(key)
                if not isinstance(text, str) or not text.strip():
                    problems.append("%s: inline command has no summary in %s under the key %r. Review the "
                                    "summary against the command, then key it so" % (label, INLINE, key))
                else:
                    hook_rows.append([key_cell("inline: " + label), "hook", event, cell(matcher), cell(cond), *NO_MODEL, cell(text, CELL_CAP)])
                used.add(key)
                continue
            path = found.group(1)
            what = script_row(path, label, event, hook.get("command", ""))
            if what:
                model, effort = models.get(path, NO_MODEL)
                hook_rows.append([key_cell(path), "hook", event, cell(matcher), cell(cond), model, effort, cell(what, CELL_CAP)])
        elif kind in ("prompt", "agent"):
            prompt = hook.get("prompt", "")
            key = first_sentence(prompt)
            if not key:
                problems.append("%s: prompt has no first sentence" % label)
                continue
            hook_rows.append([key_cell(key), "judge", event, cell(matcher), cell(cond), hook.get("model") or "unset", "n/a",
                              cell(judge_text(prompt, key), CELL_CAP)])
        else:
            problems.append("%s: hook type %r has no catalog reader" % (label, kind))

    problems += ["%s has an entry that matches no inline command: %s" % (INLINE, k) for k in inline if k not in used]

    mod_rows, external = [], []
    for plugin, on in settings.get("enabledPlugins", {}).items():
        name, _, source = plugin.partition("@")
        if on is not True:
            continue
        if source != "claude-settings":
            external.append(name)
            continue
        base = "mods/" + name
        if has_file(base + "/README.md"):
            text = under_first_heading(read(base + "/README.md"))
        else:
            text = mod_manifest_description(base) if has_file(base + "/SOURCE.md") else ""
        if not text:
            problems.append("%s: no text under the first heading of README.md, and no plugin.json description with a SOURCE.md" % base)
            continue
        mod_rows.append([key_cell("mods/" + name), "mod", "-", "-", "-", "not listed", "not listed", cell(text, CELL_CAP)])

    skill_rows = []
    for name in skill_names(os.path.join(ROOT, "skills")):
        text = frontmatter_description(read("skills/%s/SKILL.md" % name))
        if not text:
            problems.append("skills/%s: SKILL.md has no description in its frontmatter" % name)
            continue
        skill_rows.append([key_cell("skills/" + name), "skill", "-", "-", "-", "no model", "none", cell(text, CELL_CAP)])

    page = INTRO % {"regen": REGEN}
    page += table("Hooks and judges", hook_rows) + table("Mods", mod_rows) + table("Skills", skill_rows)
    if external:
        page += ("## External plugins\n\nThese plugins are enabled in `settings.json`. They are not in this repo, "
                 "so this page gives no description.\n\n" + "".join("- %s: not in this repo\n" % n for n in external))
    return page.rstrip("\n") + "\n", problems


# ---- the records page --------------------------------------------------------------------------

RECORDS_PAGE = layout.layout()["kinds"]["records-index"]["path"]
SECTIONS = ("Mandates", "Rulings", "Build designs", "Unsorted decisions", "Debts", "Plans")
RULE_MARK = re.compile(r"<!--\s*rule:([a-z0-9][a-z0-9-]*)\s*-->")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
KIND = re.compile(r"^Kind:\s*(process|build)\s*$")
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
# A marker opens overruled text. "No longer" is a marker only as "No longer in force": "No longer used: x" is plain prose.
# A hyphen after a marker joins it to another word ("Previously-run tests"), so it is no marker.
OPENS_HISTORY = re.compile(r"(?:superseded|overruled|previously|old ruling|no longer in force)(?![A-Za-z0-9-])", re.I)
WAS_COLON = re.compile(r"\bwas:", re.I)
OLD_WORD = re.compile(r"\bold\b", re.I)

RECORDS_INTRO = """# Records index

This page lists every record in this repo: the rules in `CLAUDE.md`, and the files in {folders}. A script writes it. Do not edit it by hand.

The merge tool writes this page again when a pull request merges, so a pull request need not carry a fresh one. To write it by hand, run `python3 lint/hook_catalog.py` from the claude-settings checkout, with `--root` set to this repo. The check on the default branch fails when the page is stale.

Each row has the slug, the first sentence of the record, and a link to it. A record that a ruling overrules is rewritten in place, so no row holds old text.

"""


def lines_outside_fences(text):
    """(line number from 1, line) for each line. A line inside a fenced block, the fences too, has line None.
    A fence closes on the same character, at least as long, with no text after it (CommonMark)."""
    fence = None
    for n, line in enumerate(text.split("\n"), 1):
        found = FENCE.match(line)
        if fence:
            if found and found.group(1)[0] == fence[0] and len(found.group(1)) >= len(fence) and not found.group(2).strip():
                fence = None
            yield n, None
        elif found and not (found.group(1)[0] == "`" and "`" in found.group(2)):
            fence = found.group(1)
            yield n, None
        else:
            yield n, line


def mask_code(text):
    """text with each inline code span turned into NUL characters, newlines kept, so every index stays valid."""
    return CODE_SPAN.sub(lambda m: re.sub(r"[^\n]", "\0", m.group(0)), text)


def blocks(text):
    """The blocks outside fences, as [first line number, kind, lines]. Kind: heading, item (a list item and its
    continuation lines) or para. A blank line, a fence, a heading and a new list item each end the block before them."""
    out, cur = [], None
    for n, line in lines_outside_fences(text):
        if line is None or not line.strip():
            cur = None
        elif HEADING.match(line):
            out.append([n, "heading", [line]])
            cur = None
        elif ITEM.match(line):
            cur = [n, "item", [line]]
            out.append(cur)
        elif cur:
            cur[2].append(line)
        else:
            cur = [n, "para", [line]]
            out.append(cur)
    return out


def raw_of(block):
    """The lines of a block, joined, without the heading hashes or the list marker."""
    _n, kind, lines = block
    first = lines[0]
    if kind == "heading":
        first = re.sub(r"[ \t]+#+$", "", HEADING.match(first).group(2) or "")
    elif kind == "item":
        first = ITEM.sub("", first, 1)
    return "\n".join([first] + lines[1:])


def sentence(text):
    """The first sentence of flat text: up to the first '. ', '? ' or '! ', else all of it. A code span never ends it."""
    found = re.search(r"[.?!](?=\s)", mask_code(text))
    return text[:found.end()] if found else text


def history_problems(rel, text):
    """One line per place a record keeps overruled text: <path>:<line>. Fences and inline code are never read."""
    out = []
    for n, kind, lines in blocks(text):
        masked = mask_code("\n".join(lines)).split("\n")
        for i, line in enumerate(masked):
            hit = None
            body = raw_of([n, kind, [line]]).lstrip("*_ \t") if i == 0 else ""
            if i == 0:  # a marker counts where it opens a heading, a paragraph or a list item
                found = OPENS_HISTORY.match(body)
                hit = found.group(0) if found else None
            if not hit:  # "was:" introduces old text when it opens a block, or when the word "old" comes before it in the block
                found = WAS_COLON.search(line)
                if found and (body[:4].lower() == "was:" or OLD_WORD.search("\n".join(masked[:i] + [line[:found.start()]]))):
                    hit = "was:"
            if hit:
                out.append("%s:%d: overruled text (%s). Rewrite the record in place and delete the old text" % (rel, n + i, hit))
    return out


def mandates(text):
    """[(rule id, gist)] in file order. A rule's text runs from its paragraph start, or the marker before it, to its marker."""
    found, seen = [], set()
    for block in blocks(text):
        raw = raw_of(block)
        start = 0
        for mark in RULE_MARK.finditer(mask_code(raw)):
            seg = raw[start:mark.start()]
            if start == 0:
                seg = re.sub(r"^\s*\*\*[^*\n]+\*\*\s*", "", seg)  # a bold lead label is no part of the rule
            start = mark.end()
            if mark.group(1) not in seen:
                seen.add(mark.group(1))
                found.append((mark.group(1), sentence(flat(seg))))
    return found


def block_gist(block):
    """The first sentence of a block. A table is no sentence: "" ."""
    raw = raw_of(block)
    if raw.lstrip().startswith("|"):
        return ""
    return sentence(flat(re.sub(r"(?m)^[ \t]*>[ \t]?", "", raw)))


def decision_gist(text):
    """The first block under `## Ruling` or `## The ruling`, else under `## The question`, else the first paragraph
    under the H1, else the H1 text."""
    found = blocks(text)

    def under(i):
        return block_gist(found[i + 1]) if i + 1 < len(found) and found[i + 1][1] != "heading" else ""

    def level(i):
        return HEADING.match(found[i][2][0]).group(1)

    def section(want):
        for i, block in enumerate(found):
            if block[1] == "heading" and level(i) == "##" and re.fullmatch(want, flat(raw_of(block)), re.I):
                return i
        return None

    ruling = section(r"(?:the )?ruling")
    if ruling is not None and under(ruling):
        first = flat(raw_of(found[ruling + 1]))
        question = section(r"the question")
        # A ruling of under 4 words ("Yes.", "Owner, 2026-10-11:") says nothing alone: the question's first sentence does.
        if len(first.split()) < 4 and question is not None and under(question):
            return under(question)
        return under(ruling)
    question = section(r"the question")
    if question is not None and under(question):
        return under(question)
    for i, block in enumerate(found):
        if block[1] == "heading" and level(i) == "#":
            return under(i) or flat(raw_of(block))
    return ""


def debt_gist(text):
    """The first sentence of the **What.** item."""
    for block in blocks(text):
        found = re.match(r"\*\*What\.\*\*\s*", raw_of(block))
        if found:
            return sentence(flat(raw_of(block)[found.end():]))
    return ""


def first_line_gist(text):
    """The first line that has text, its leading # dropped."""
    for line in text.split("\n"):
        if line.strip():
            return flat(re.sub(r"^\s*#+\s*", "", line))
    return ""


def decision_section(text):
    kinds = {m.group(1) for _n, line in lines_outside_fences(text) if line is not None for m in [KIND.match(line)] if m}
    return {frozenset(["process"]): "Rulings", frozenset(["build"]): "Build designs"}.get(frozenset(kinds), "Unsorted decisions")


def listed_folders():
    """(kind, folder) for each kind the records page lists, in layout order."""
    return [(kind, layout.path(ROOT, kind)) for kind, found in layout.kinds(ROOT).items() if found.get("listed")]


def collect_records():
    """({section: [(slug, gist, link text, link)]}, problems). A page is written only when no problem stands."""
    rows = {name: [] for name in SECTIONS}
    problems = []
    if has_file("CLAUDE.md"):
        text = read("CLAUDE.md")
        problems += history_problems("CLAUDE.md", text)
        for rule, gist in mandates(text):
            if gist:
                rows["Mandates"].append((rule, gist, "CLAUDE.md", "../CLAUDE.md"))
            else:
                problems.append("CLAUDE.md: the rule %s has no text before its marker" % rule)
    notes = layout.path(ROOT, "debt-notes")  # the notes tier: one line per unlikely finding, not a record
    for kind, folder in listed_folders():
        base = os.path.join(ROOT, *folder.split("/"))
        try:
            names = sorted(os.listdir(base)) if os.path.isdir(base) else []
        except OSError as err:
            raise Unreadable(folder) from err
        for name in names:
            rel = "%s/%s" % (folder, name)
            if not name.endswith(".md") or name == "README.md" or not has_file(rel):
                continue
            text = read(rel)
            problems += history_problems(rel, text)
            if rel == notes:
                continue
            if kind == "decisions":
                section, gist = decision_section(text), decision_gist(text)
            elif kind == "debts":
                section, gist = "Debts", debt_gist(text)
            else:
                section, gist = kind.capitalize(), first_line_gist(text)
            if gist:
                rows.setdefault(section, []).append((name[:-3], gist, rel, "../" + rel))
            else:
                problems.append("%s: %s" % (rel, "no **What.** line to make a gist from" if kind == "debts" else "no text to make a gist from"))
    return rows, problems


def render_records():
    """(page text, problems). The page is "" for a repo with no records: it gets none."""
    rows, problems = collect_records()
    if not any(rows.values()):
        return "", problems
    listed = ["`%s/`" % folder for _kind, folder in listed_folders()]
    page = RECORDS_INTRO.replace("{folders}", ", ".join(listed[:-1]) + " and " + listed[-1] if len(listed) > 1 else "".join(listed))
    for name in rows:  # SECTIONS first, then each extra kind a repo lists
        found = rows[name] if name == "Mandates" else sorted(rows[name])
        if found:
            page += "## %s\n\n| Slug | Gist | Link |\n|---|---|---|\n" % name
            page += "".join("| `%s` | %s | [`%s`](%s) |\n" % (slug, gist.replace("|", "\\|"), text, link) for slug, gist, text, link in found)
            page += "\n"
    return page.rstrip("\n") + "\n", problems


def pull_request_run():
    """True on a pull request run in Actions, as the stamp engine reads it (onDefaultBranch)."""
    return bool(os.environ.get("GITHUB_BASE_REF")) or os.environ.get("GITHUB_REF", "").startswith("refs/pull/")


def has_catalog_parts():
    return any(os.path.isdir(os.path.join(ROOT, part)) for part in ("hooks", "skills", "mods"))


def emit(text):
    """Write UTF-8 to stdout, whatever the console codepage."""
    sys.stdout.flush()
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def main(argv):
    global ROOT
    parser = argparse.ArgumentParser(description="Write docs/catalog.md and docs/records.md.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print", action="store_true", dest="show", help="write the catalog page to stdout, exit 1 on a problem")
    mode.add_argument("--check", action="store_true", help="exit 1 when a page is stale or a source is empty or keeps overruled text")
    parser.add_argument("--records-only", action="store_true", help="write or check docs/records.md alone: no catalog, no settings.json read. The merge tool runs this mode")
    parser.add_argument("--root", help="the repo root. The default is the environment variable HOOK_CATALOG_ROOT, else the repo this script is in")
    args = parser.parse_args(argv)
    if args.records_only and args.show:
        parser.error("--records-only and --print cannot go together: --print writes the catalog")
    ROOT = os.path.abspath(args.root or os.environ.get("HOOK_CATALOG_ROOT") or os.path.dirname(HERE))
    try:
        pages, problems = {}, []
        if has_catalog_parts() and not args.records_only:
            pages[PAGE], problems = render()
        if args.show:
            emit(pages.get(PAGE, ""))
            sys.stderr.write("".join("hook_catalog: %s\n" % p for p in problems))
            return 1 if problems else 0
        records, more = render_records()
        problems += more
        if records:
            pages[RECORDS_PAGE] = records
        if not problems and args.check:
            for rel, page in pages.items():
                state = "missing" if not has_file(rel) else "stale" if read(rel) != page else ""
                # The merge tool rewrites the records page on the pull request head, so a pull request run waives it.
                if state and not (rel == RECORDS_PAGE and pull_request_run()):
                    problems.append("%s is %s: run %s" % (rel, state, REGEN))
        if problems:
            emit("".join(p + "\n" for p in problems))
            return 1
        if not args.check:
            for rel, page in pages.items():
                if has_file(rel) and read(rel) == page:
                    continue
                target = os.path.join(ROOT, *rel.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(page)
                emit("wrote %s\n" % rel)
        return 0
    except Unreadable as err:
        emit("hook_catalog: cannot read %s\n" % err)
        return 2
    except layout.LayoutError as err:
        emit("hook_catalog: cannot read the layout: %s\n" % err)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
