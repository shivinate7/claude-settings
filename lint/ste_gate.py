#!/usr/bin/env python3
"""Claude Code hook: Simplified Technical English gate.

Reads the hook JSON on stdin. Runs the vendored ste_lint.py next to this file at error
severity only. Prints JSON when there is something to say. Always exits 0.

PreToolUse on Write, Edit, MultiEdit for a *.md path, or a UI file (ste_lint.UI_SUFFIXES:
.tsx, .jsx, .html, .vue): deny the write when the new text has STE errors, and hand the
findings back so the writer fixes them first. For a UI file ste_lint reads only the copy a
user sees, never the code.

AUTO-FIX. For a Markdown file the hook first runs ste_lint.apply_fixes on the changed blocks
and returns the fixed text through updatedInput (rewrite_output, the one rewrite function).
It denies only for the errors that remain. A UI file is never fixed. A fixer crash falls
back to the plain lint: no rewrite, never a refusal.

SCOPING TO CHANGED BLOCKS. This hook sees the proposed content before the write lands. It
replays the tool's own edit onto the file currently on disk to get the FULL proposed text,
the same content the write would leave behind, then lints only the BLOCKS that differ from
disk. A block is a paragraph, a run of lines bounded by blank lines: STE001 is a sentence
rule and a sentence can run over more than one line, reported at the line it starts on, so a
plain line filter could drop a finding whose sentence starts outside the edit. A sentence
never crosses a blank line, so filtering by block instead of by line closes that hole.

A file that does not exist on disk yet is entirely new, so it lints in full. So does a Write
or Edit this hook cannot replay onto disk content alone, an Edit whose `old_string` is not on
disk, or matched more than once without `replace_all`: rather than guess which blocks
changed, it lints the whole proposed text, the strict, no-worse-than-before default.
"""
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _transcript import paragraph_blocks, format_finding  # noqa: E402
try:
    import ste_lint  # noqa: E402
    from ste_lint import UI_SUFFIXES  # noqa: E402
except Exception:
    ste_lint = None
    UI_SUFFIXES = set()  # no linter next to this file: main() returns before it lints

MD_SUFFIXES = (".md", ".markdown")
MAX_SHOWN = 5
CLAUSE_WORDS = {"and", "but", "which", "because", "so", "then", "while", "when", "if"}
NOTE = ("Code in backticks or a fence is exempt. Errors only: sentence length, nominalization, "
        "Latin abbreviation, contraction, phrasal verb, bloat, double negative, "
        "condition order, omitted 'that'.")
UI_NOTE = ("UI file: only the copy a user sees is read. Contraction and condition order do not "
           "apply. A button, label or aria-label holds 4 words at most.")


def lint(linter, text, suffix=".md", config_from=None):
    """Return the error-level findings of ste_lint.py on text, as finding dicts, or None
    when the lint could not run (a timeout, a crash, output that is not JSON). `suffix`
    picks the reader: ste_lint reads a UI suffix as UI copy, and anything else as Markdown.
    `config_from` is the real target path, so the repo's .ste.json still applies."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "gate" + suffix)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            run = subprocess.run(
                [sys.executable, linter, "--no-color", "--format", "json", "--fail-on", "never"]
                + (["--config-from", config_from] if config_from else []) + [path],
                capture_output=True, text=True, timeout=15,
            )
            data = json.loads(run.stdout)
        except Exception:
            return None
    return [f for f in data.get("findings", []) if f.get("severity") == "error"]


# paragraph_blocks and format_finding live in lint/_transcript.py, imported above. This hook,
# lint/md_sweep.py, lint/report_gate.py, and hooks/decision_watch.py share that one copy;
# hooks/decision_watch.py already imports lint/report_gate.py, which already imports this
# module, so the readers these hooks share are no longer split one-per-file.

# ------------------------------------------------------------------ scoping to changed blocks

def changed_new_lines(old_text, new_text):
    """Return the 1-indexed lines of `new_text` that differ from `old_text`.

    A pure deletion, text removed with nothing put in its place, has no line of its own in
    `new_text`. Both the line before and the line after the point it sat at are counted as
    changed instead, so the block on either side of a deletion is still caught.
    """
    old_lines = old_text.split("\n")
    new_lines = new_text.split("\n")
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    changed = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if j2 > j1:
            changed.update(range(j1 + 1, j2 + 1))
        else:
            changed.add(j1 + 1)
            if j1 > 0:
                changed.add(j1)
    return changed


def scope_of_change(old_text, new_text):
    """Return the lines of `new_text` in scope for linting: every line of every block that
    differs from `old_text`. Empty when the two texts are identical."""
    changed = changed_new_lines(old_text, new_text)
    if not changed:
        return set()
    in_scope = set()
    for start, end in paragraph_blocks(new_text):
        if any(n in changed for n in range(start, end + 1)):
            in_scope.update(range(start, end + 1))
    return in_scope


def ui_scope_of_change(old_text, new_text, suffix):
    """For a UI file: return the lines of every copy unit (a text block, an attribute
    value, a comment line) of `new_text` whose text is not a unit of `old_text`. Code
    lines and old copy the edit did not touch are never in scope. A block-level scope
    does not work here: a component often holds no blank line at all."""
    old = [t for t, _ in ste_lint.ui_units("x" + suffix, old_text)]
    new = ste_lint.ui_units("x" + suffix, new_text)
    # Compare by position: a new unit that repeats old text elsewhere is still new.
    matcher = difflib.SequenceMatcher(None, old, [t for t, _ in new], autojunk=False)
    scope = set()
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            for _, lines in new[j1:j2]:
                scope.update(lines)
    return scope


def apply_edit(text, old_string, new_string, replace_all):
    """Return `text` with `old_string` replaced by `new_string`, the way the Edit tool itself
    resolves a replacement, or None when that cannot be resolved from `text` alone:
    `old_string` empty or absent, or present more than once without `replace_all`.
    """
    if not old_string:
        return None
    count = text.count(old_string)
    if count == 0:
        return None
    if replace_all:
        return text.replace(old_string, new_string)
    if count > 1:
        return None
    index = text.find(old_string)
    return text[:index] + new_string + text[index + len(old_string):]


def resolve(tool, ti, old_text):
    """Return (text, resolved) for a Write, Edit or MultiEdit input. `text` is the new text
    the tool carries. `resolved` is the full proposed file, or None when the edit cannot be
    replayed against `old_text` alone."""
    resolved = None
    if tool == "Write":
        text = ti.get("content") or ""
        resolved = text
    elif tool == "Edit":
        text = ti.get("new_string") or ""
        if old_text is not None:
            resolved = apply_edit(old_text, ti.get("old_string") or "", text,
                                   bool(ti.get("replace_all")))
    else:  # MultiEdit
        edits = ti.get("edits") or []
        text = "\n\n".join((e or {}).get("new_string") or "" for e in edits)
        if old_text is not None:
            resolved = old_text
            for e in edits:
                e = e or {}
                resolved = apply_edit(resolved, e.get("old_string") or "",
                                      e.get("new_string") or "", bool(e.get("replace_all")))
                if resolved is None:
                    break
    return text, resolved


# ------------------------------------------------------------------ the fixer (Markdown only)

def fix_fragment(context, idx, old_len, fragment):
    """Return `fragment` fixed by ste_lint.apply_fixes as it reads at `idx` in `context`
    (where it replaces `old_len` characters), or None when it sits in front matter or a code
    fence, or its fix reaches past its own text. The fixer reads the real line around the
    fragment, so an open code span, link or indent is known. The text around the fragment is
    fixed in a second run, and the fragment's fix must leave it as that run did."""
    head = context[:idx]
    line_start = head.rfind("\n") + 1
    if head.count("\n") < ste_lint.front_matter_lines(context):
        return None
    state = None
    for line in head[:line_start].split("\n"):
        state = ste_lint.fence_step(state, line)
    if state is not None:
        return None
    prefix = head[line_start:]
    tail = context[idx + old_len:].split("\n", 1)[0]
    mark = "\x01"
    keep, _ = ste_lint.apply_fixes(prefix + mark + tail)
    fixed, _ = ste_lint.apply_fixes(prefix + fragment + tail)
    left, right = keep.split(mark)
    if not (fixed.startswith(left) and fixed.endswith(right)) or len(fixed) < len(left + right):
        return None
    return fixed[len(left):len(fixed) - len(right)]


def fix_edit(context, old_string, new_string, replace_all):
    """Fix the `new_string` of one Edit, in the context of the text it lands in. `context` is
    None when the edit cannot be replayed: the string is then fixed on its own."""
    if context is None or not old_string or old_string not in context:
        return fix_fragment("", 0, 0, new_string)
    spots, at = [], context.find(old_string)
    while at != -1:
        spots.append(at)
        at = context.find(old_string, at + len(old_string))
    if len(spots) > 1 and not replace_all:
        return fix_fragment("", 0, 0, new_string)
    results = {fix_fragment(context, i, len(old_string), new_string) for i in spots}
    return results.pop() if len(results) == 1 else None


def autofix(tool, ti, old_text, scope):
    """Return (updated tool input, codes fixed), or None when nothing changed. `scope` is the
    set of changed lines of a Write, or None for all. A Write is fixed as a whole file, so the
    fences are read right, and only the lines in scope keep their fix. The fix never changes
    the line count. An Edit chain that the fix would break (a later `old_string` no longer
    matches) is not rewritten at all."""
    new_ti, codes = dict(ti), []
    if tool == "Write":
        content = ti.get("content") or ""
        fixed, _ = ste_lint.apply_fixes(content)
        old_lines, new_lines = content.split("\n"), fixed.split("\n")
        if len(old_lines) != len(new_lines):
            raise ValueError("the fixer changed the line count")
        for n, (a, b) in enumerate(zip(old_lines, new_lines), 1):
            if a != b and (scope is None or n in scope):
                old_lines[n - 1] = b
                codes += ste_lint.LAST_FIX_CODES.get(n, [])
        new_ti["content"] = "\n".join(old_lines)
    else:
        edits = [ti] if tool == "Edit" else [e or {} for e in ti.get("edits") or []]
        context, fixed_edits = old_text, []
        for e in edits:
            new = e.get("new_string") or ""
            fixed = fix_edit(context, e.get("old_string") or "", new, bool(e.get("replace_all")))
            if fixed is not None and fixed != new:
                codes += [c for v in ste_lint.LAST_FIX_CODES.values() for c in v]
                e = dict(e, new_string=fixed)
            fixed_edits.append(e)
            if context is not None:
                context = apply_edit(context, e.get("old_string") or "", e.get("new_string") or "",
                                     bool(e.get("replace_all")))
        if tool == "Edit":
            new_ti = fixed_edits[0]
        else:
            new_ti["edits"] = fixed_edits
        if (old_text is not None and resolve(tool, ti, old_text)[1] is not None
                and resolve(tool, new_ti, old_text)[1] is None):
            return None
    return (new_ti, codes) if new_ti != ti else None


def fixer_limit():
    """Seconds the fixer may run: env STE_FIXER_LIMIT_S, default 5."""
    try:
        return float(os.environ.get("STE_FIXER_LIMIT_S", "5"))
    except ValueError:
        return 5.0


def run_autofix(tool, ti, old_text, scope):
    """Run autofix in a thread, bounded by fixer_limit(). Return its result, or raise
    TimeoutError when it ran over, or its own error: the caller then lints the plain text.
    ponytail: a thread cannot stop a regex stuck in C code. The fixer's patterns are
    linear, so a subprocess waits until one measures slow."""
    box = []

    def work():
        try:
            box.append((True, autofix(tool, ti, old_text, scope)))
        except Exception as exc:  # noqa: BLE001
            box.append((False, exc))
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(fixer_limit())
    if not box:
        raise TimeoutError("the STE fixer ran over its time limit")
    ok, value = box[0]
    if not ok:
        raise value
    return value


def rewrite_output(updated_input, note):
    """The one PreToolUse rewrite. It carries no permissionDecision: "allow" would approve
    the call, and "defer" makes Claude Code drop updatedInput. Deny and ask rules still apply
    to the rewritten input. Later rewrites reuse this function."""
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": updated_input,
                                   "additionalContext": note},
            "systemMessage": note}


def split_hint(text, line, limit):
    """Return a short split point for the sentence that starts at `line` of `text`: a clause
    break before word `limit`, else word `limit`."""
    block = []
    for ln in text.split("\n")[line - 1:]:
        if not ln.strip():
            break
        block.append(ln)
    words = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", " ".join(block)).split()
    end = next((i for i, w in enumerate(words) if re.search(r"[.!?]$", w)), len(words))
    words = words[:end + 1]
    cut = next((i for i in range(min(limit, len(words) - 1) - 1, 3, -1)
                if re.search(r"[,;:]$", words[i]) or words[i + 1].lower() in CLAUSE_WORDS), None)
    cut = limit - 1 if cut is None else cut
    return 'Split after word %d, "%s".' % (cut + 1, " ".join(words[max(0, cut - 3):cut + 1]))


def deny_reason(path, findings, text, is_ui):
    """The denial text. It lists 5 findings at most. A sentence-length finding names the
    sentence start, its word count, the limit, and one split point."""
    lines = []
    for f in findings[:MAX_SHOWN]:
        line = format_finding(f)
        m = re.search(r"holds (\d+) words\. The \w+ limit is (\d+)", f.get("message") or "")
        if f.get("code") == "STE001" and m and not is_ui:
            line += '\n  Starts: "%s". %s' % (
                (f.get("excerpt") or "")[:60], split_hint(text, f.get("line") or 1, int(m.group(2))))
        lines.append(line)
    if len(findings) > MAX_SHOWN:
        lines.append("%d more findings not shown." % (len(findings) - MAX_SHOWN))
    return ("STE lint on the text for %s:\n%s\n%s Fix the text, then write again. For a "
            "rule's meaning, run `python3 %s --explain <id>`." % (
                os.path.basename(path), "\n".join(lines), UI_NOTE if is_ui else NOTE,
                os.path.join(HERE, "ste_lint.py")))


def last_reply(hook):
    text = hook.get("last_assistant_message")
    if text:
        return text
    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return ""
    text = ""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "assistant":
                    continue
                parts = [b.get("text", "") for b in (rec.get("message") or {}).get("content", [])
                         if isinstance(b, dict) and b.get("type") == "text"]
                if parts:
                    text = "\n".join(parts)
    except Exception:
        return ""
    return text


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(hook, dict):
        return
    linter = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ste_lint.py")
    if not os.path.exists(linter):
        return
    event = hook.get("hook_event_name")

    if event == "PreToolUse":
        tool = hook.get("tool_name")
        ti = hook.get("tool_input") or {}
        path = ti.get("file_path") or ""
        suffix = os.path.splitext(path)[1].lower()
        if not path.lower().endswith(MD_SUFFIXES) and suffix not in UI_SUFFIXES:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                old_text = f.read()
        except Exception:
            old_text = None  # no file on disk yet: entirely new, lint in full

        if tool not in ("Write", "Edit", "MultiEdit"):
            return
        # `resolved` holds the full proposed content once known. None means the edit could
        # not be replayed against disk content alone, so the fallback text below is linted
        # in full rather than guessed at.
        text, resolved = resolve(tool, ti, old_text)
        is_ui = suffix in UI_SUFFIXES

        if old_text is None or resolved is None:
            scope = None  # new file, or an edit this hook could not replay: lint in full
            full_text = resolved if resolved is not None else text
        else:
            full_text = resolved
            if is_ui:
                scope = ui_scope_of_change(old_text, full_text, suffix)
            else:
                scope = scope_of_change(old_text, full_text)

        # Markdown only: fix what a word swap fixes, then lint the fixed text. A fixer crash
        # keeps today's behaviour (decisions/gate-hooks-fail-closed.md): no rewrite, no refusal.
        fixed_ti, note = None, ""
        if not is_ui:
            try:
                result = run_autofix(tool, ti, old_text, scope)
                if result:
                    fixed_ti, codes = result
                    text, resolved = resolve(tool, fixed_ti, old_text)
                    full_text = resolved if resolved is not None else text
                    counts = ["%s x%d" % (c, codes.count(c)) for c in sorted(set(codes))]
                    note = "STE lint fixed %s in %s." % (
                        ", ".join(counts) or "wording", os.path.basename(path))
            except Exception:
                fixed_ti, note = None, ""

        findings = lint(linter, full_text, suffix if is_ui else ".md", path)
        if findings is None:
            # "Report a read that could not run as unknown, never as clear or broken."
            # The write goes ahead, and the message says that nobody checked it.
            unknown = ("STE lint could not run on the text for %s. The result is unknown: the "
                       "write was not checked." % os.path.basename(path))
            print(json.dumps(rewrite_output(fixed_ti, note + " " + unknown) if fixed_ti
                             else {"systemMessage": unknown}))
            return
        if scope is not None:
            findings = [f for f in findings if f.get("line") in scope]
        if findings:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_reason(path, findings, full_text, is_ui),
            }}))
        elif fixed_ti:
            print(json.dumps(rewrite_output(fixed_ti, note)))


if __name__ == "__main__":
    main()
