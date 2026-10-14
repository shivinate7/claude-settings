#!/usr/bin/env python3
"""Writes docs/catalog.md, one page that says what each hook, judge, mod and skill does.

The owner asked for this page on 2026-10-13: plain words, one row each, and the model and
effort beside it, like the model table in decisions/subagent-model-cap.md. The page is
generated and never edited by hand. Each description comes from the source it describes, so
the page cannot drift from it.

    python3 lint/hook_catalog.py            write docs/catalog.md
    python3 lint/hook_catalog.py --print    write the page to stdout, exit 0
    python3 lint/hook_catalog.py --check    exit 0 and print nothing when the page is current

The root is the repo root, or the folder in the environment variable HOOK_CATALOG_ROOT.

Sources, all read from the root:
  settings.json `hooks`   one row per registration (event, matcher, `if`, command or prompt).
  a command's script      the first paragraph of a .py docstring, or the leading comment block
                          of a .sh script, after an optional shebang.
  a prompt hook           the key is its first sentence. The text is the rest of the prompt,
                          up to the clause that blocks only on a clear breach.
  enabled repo mods       `enabledPlugins` keys `<name>@claude-settings` set true. The text is
                          the intro under the first heading of mods/<name>/README.md, or of
                          mods/<name>/SOURCE.md when the mod has no README.
  skills                  the `description` in the frontmatter of skills/<name>/SKILL.md.
  model and effort        the row of the model table whose first cell names the script.

Exits 1 and prints one line per problem when a source is missing or empty, or the page is
stale. Exits 2 and names the path when an input cannot be read. Writing the page refuses to
run while a problem stands.
"""
import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_skill_model_rows import skill_names  # noqa: E402  one home for "a skill is a folder with SKILL.md"

ROOT = os.path.abspath(os.environ.get("HOOK_CATALOG_ROOT") or os.path.dirname(HERE))
PAGE = "docs/catalog.md"
TABLE = "decisions/subagent-model-cap.md"
REGEN = "python3 lint/hook_catalog.py"
COLUMNS = ["Key", "Kind", "Event", "Matcher", "If", "Model", "Effort", "What it does"]
CMD_PATH = re.compile(r"\$\{CLAUDE_CONFIG_DIR:-\$HOME/\.claude\}/([\w./-]+\.(?:py|sh|mjs|js))")
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


def cell(text):
    """One table cell: one line, a pipe written \\|, and <tag> text in a code span so a viewer shows it."""
    parts = re.split(r"(`[^`]*`)", flat(text))
    text = "".join(p if p.startswith("`") else re.sub(r"<[^<>\s][^<>]*>", r"`\g<0>`", p) for p in parts)
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
    """The first paragraph of the module docstring. Parsed with ast, never scanned."""
    return flat((ast.get_docstring(ast.parse(text)) or "").strip().split("\n\n")[0])


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


def model_table():
    """{script path: (model, effort)} for each model-table row that names a script."""
    found = {}
    for line in read(TABLE).split("\n"):
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

- A hook runs a script. Its text is the first paragraph of the script docstring, or the leading comment block of a shell script.
- A judge is a prompt hook that a model answers. Its key is the first sentence of the prompt. Its text is the rest of the prompt, up to the standard clause that blocks only on a clear breach.
- A mod is an enabled mod from this repo. Its text is the intro of its `README.md`, or of its `SOURCE.md` when it has no README.
- A skill is a folder under `skills/`. Its text is the `description` in its `SKILL.md` frontmatter.

Model and effort come from the model table (decision `subagent-model-cap`, the model per role). A hook with no row in that table calls no model, so its row says "no model". A judge takes the `model` field of its prompt hook, and a prompt hook has no effort field. A skill has no model pin, so its row says "no model" and effort "none". The model table has no row for a mod, so a mod row says "not listed". A mod may still call a model.

"""


def key_cell(text):
    return cell(text) if "`" in text else "`%s`" % cell(text)


def table(title, rows):
    out = ["## " + title, "", "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out) + "\n\n"


def label_of(event, matcher, cond):
    return event + ("" if matcher == "-" else " matcher=" + matcher) + ("" if cond == "-" else " if=" + cond)


def render():
    """(page text, problems). A problem is one line that names its offender."""
    settings = load_settings()
    models = model_table()
    problems, hook_rows, docs = [], [], {}

    def script_row(path, label):
        if path not in docs:
            text = read(path)
            ext = path.rsplit(".", 1)[1]
            try:
                docs[path] = py_doc(text) if ext == "py" else sh_doc(text) if ext == "sh" else None
            except SyntaxError as err:
                problems.append("%s: cannot parse %s (%s)" % (label, path, err.msg))
                docs[path] = ""
            else:
                if docs[path] is None:
                    problems.append("%s: %s is a .%s file, and only .py and .sh have a docstring reader" % (label, path, ext))
                elif not docs[path]:
                    problems.append("%s: %s has no docstring (a .py docstring, or a .sh comment block after the shebang)" % (label, path))
                elif ext == "py" and path not in models and calls_invoke_model(text):
                    problems.append("%s: %s calls invoke_model but has no model-table row" % (label, path))
        return docs[path]

    for event, matcher, cond, hook in registrations(settings):
        label = label_of(event, matcher, cond)
        kind = hook.get("type")
        if kind == "command":
            found = CMD_PATH.search(hook.get("command", ""))
            if not found:
                problems.append("%s: command names no script (inline shell)" % label)
                continue
            path = found.group(1)
            what = script_row(path, label)
            if what:
                model, effort = models.get(path, NO_MODEL)
                hook_rows.append([key_cell(path), "hook", event, cell(matcher), cell(cond), model, effort, cell(what)])
        elif kind in ("prompt", "agent"):
            prompt = hook.get("prompt", "")
            key = first_sentence(prompt)
            if not key:
                problems.append("%s: prompt has no first sentence" % label)
                continue
            hook_rows.append([key_cell(key), "judge", event, cell(matcher), cell(cond), hook.get("model") or "unset", "n/a",
                              cell(judge_text(prompt, key))])
        else:
            problems.append("%s: hook type %r has no catalog reader" % (label, kind))

    mod_rows, external = [], []
    for plugin, on in settings.get("enabledPlugins", {}).items():
        name, _, source = plugin.partition("@")
        if on is not True:
            continue
        if source != "claude-settings":
            external.append(name)
            continue
        found = [f for f in ("README.md", "SOURCE.md") if has_file("mods/%s/%s" % (name, f))]
        text = under_first_heading(read("mods/%s/%s" % (name, found[0]))) if found else ""
        if not text:
            problems.append("mods/%s: no text under the first heading of README.md or SOURCE.md" % name)
            continue
        mod_rows.append([key_cell("mods/" + name), "mod", "-", "-", "-", "not listed", "not listed", cell(text)])

    skill_rows = []
    for name in skill_names(os.path.join(ROOT, "skills")):
        text = frontmatter_description(read("skills/%s/SKILL.md" % name))
        if not text:
            problems.append("skills/%s: SKILL.md has no description in its frontmatter" % name)
            continue
        skill_rows.append([key_cell("skills/" + name), "skill", "-", "-", "-", "no model", "none", cell(text)])

    page = INTRO % {"regen": REGEN}
    page += table("Hooks and judges", hook_rows) + table("Mods", mod_rows) + table("Skills", skill_rows)
    if external:
        page += ("## External plugins\n\nThese plugins are enabled in `settings.json`. They are not in this repo, "
                 "so this page gives no description.\n\n" + "".join("- %s: not in this repo\n" % n for n in external))
    return page.rstrip("\n") + "\n", problems


def emit(text):
    """Write UTF-8 to stdout, whatever the console codepage."""
    sys.stdout.flush()
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def main(argv):
    parser = argparse.ArgumentParser(description="Write docs/catalog.md.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print", action="store_true", dest="show", help="write the page to stdout")
    mode.add_argument("--check", action="store_true", help="exit 1 when the page is stale or a source is empty")
    args = parser.parse_args(argv)
    try:
        page, problems = render()
        if args.show:
            emit(page)
            sys.stderr.write("".join("hook_catalog: %s\n" % p for p in problems))
            return 0
        if not problems and args.check:
            if not has_file(PAGE):
                problems.append("%s is missing: run %s" % (PAGE, REGEN))
            elif read(PAGE) != page:
                problems.append("%s is stale: run %s" % (PAGE, REGEN))
        if problems:
            emit("".join(p + "\n" for p in problems))
            return 1
        if not args.check:
            target = os.path.join(ROOT, *PAGE.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(page)
            emit("wrote %s\n" % PAGE)
        return 0
    except Unreadable as err:
        emit("hook_catalog: cannot read %s\n" % err)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
