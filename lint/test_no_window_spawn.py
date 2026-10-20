#!/usr/bin/env python3
"""No-window check: a product file that starts a child process must start it with no console window.

    python3 lint/test_no_window_spawn.py [-v]

Incident: owner report that console windows keep popping into the foreground on Windows when helper
programs (hooks, mods, tools) start a child process.

Scope: every git-tracked product file. Python: .py under hooks, janitor, merge, lint, bin, mods,
actions, testing, skills, and extensionless files there whose first line is a python shebang (bin/merge,
bin/verdict, bin/ste-changed). JavaScript: .js, .mjs, .cjs under mods and actions. Test files are not
product: test_*, *_test.py, conftest.py, *.test.mjs, *.test.js.

Python (ast; tokenize reads the markers). A call of subprocess.run, Popen, call, check_call or
check_output is an offence. The one allowed route is the shared helper hooks/_nowindow.py. That file
is the only one that calls subprocess directly, and its wrappers add CREATE_NO_WINDOW. A raw call that
passes creationflags=CREATE_NO_WINDOW still fails: one home for the flag. The helper contract is pinned
by hooks/test_nowindow.py.

JavaScript (own lexer: strings, template literals with ${} nesting, regex literals, line and block
comments). A call of spawn, exec, execFile, spawnSync, execSync or execFileSync is an offence unless its
argument tokens hold `windowsHide: true` inline. The call must be bound to child_process by an import or
a require in the same file, so a local exec() is not a call.

Exception: a marker comment with a reason, `# nowindow: <reason>` (Python) or `// nowindow: <reason>` or
`/* nowindow: <reason> */` (JavaScript), on the call's first line or the line above. A marker with no
reason excuses nothing. A marker inside a string is text, not a marker.

Ceilings, not scanned: os.system, os.popen, subprocess.getoutput and getstatusoutput; a subprocess name
referenced but not called; a windowsHide value that is not the literal true; an options object held in a
variable (it fails: the literal must be inline).

Run with python3 lint/test_no_window_spawn.py -v. Fixture classes prove the scanner. RepoScan proves
the product tree. Output on a red run lists offences per directory, per file, then each line.
"""
import ast
import io
import os
import re
import subprocess
import tokenize
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HELPER = "hooks/_nowindow.py"
PY_DIRS = ("hooks", "janitor", "merge", "lint", "bin", "mods", "actions", "testing", "skills")
JS_DIRS = ("mods", "actions")
PY_FNS = ("run", "Popen", "call", "check_call", "check_output")
JS_FNS = ("spawn", "exec", "execFile", "spawnSync", "execSync", "execFileSync")
CP_NAMES = ("child_process", "node:child_process")
MARK = re.compile(r"\bnowindow:(.*)")
IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
NUMBER = re.compile(r"[0-9][A-Za-z0-9_.]*")
JS_KEYWORDS_BEFORE_EXPR = ("return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
                           "throw", "case", "do", "else", "yield", "await")
P, I = "punct", "id"


def is_test(base):
    return base.startswith("test_") or base.endswith(("_test.py", "conftest.py", ".test.mjs", ".test.js"))


def product_kind(rel, head):
    """Return "py", "js" or None. head(rel) gives the first bytes; read only for an extensionless file."""
    top, base = rel.split("/", 1)[0], rel.rsplit("/", 1)[-1]
    if is_test(base):
        return None
    if top in PY_DIRS:
        if base.endswith(".py"):
            return "py"
        if "." not in base:
            first = head(rel).split(b"\n", 1)[0]
            if first.startswith(b"#!") and b"python" in first:
                return "py"
    if top in JS_DIRS and base.endswith((".js", ".mjs", ".cjs")):
        return "js"
    return None


def marker_lines(comments):
    """Lines where a comment holds `nowindow:` followed by a non-empty reason."""
    ok = set()
    for line, text in comments:
        m = MARK.search(text)
        if m and m.group(1).replace("*/", "").strip():
            ok.add(line)
    return ok


def excused(ok_lines, line):
    return line in ok_lines or (line - 1) in ok_lines


def py_scan(rel, src):
    """Return (offences, unknown). offences: sorted [(line, text)]. src is bytes."""
    if rel == HELPER:
        return [], None
    try:
        tree = ast.parse(src, rel)
        comments = [(t.start[0], t.string) for t in tokenize.tokenize(io.BytesIO(src).readline)
                    if t.type == tokenize.COMMENT]
    except (SyntaxError, tokenize.TokenError, ValueError) as e:
        return [], "UNKNOWN %s: %s" % (rel, e)
    ok_lines = marker_lines(comments)
    mods, fns = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.asname or a.name for a in node.names if a.name == "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess" and not node.level:
            for a in node.names:
                if a.name in PY_FNS:
                    fns[a.asname or a.name] = a.name
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in mods and f.attr in PY_FNS:
            fn = f.attr
        elif isinstance(f, ast.Name) and f.id in fns:
            fn = fns[f.id]
        else:
            continue
        if not excused(ok_lines, node.lineno):
            out.append((node.lineno, "subprocess.%s outside the no-window helper" % fn))
    return sorted(out), None


def lex_js(src):
    """Return (tokens, comments). A token is (kind, text, line); kinds: id, num, punct, str, re.
    Strings, template text and comments are never code tokens; a ${ } inside a template is code.
    A string ends at its quote or at a newline, so a lone quote stays inside its own line."""
    toks, comments, modes = [], [], []
    depth, i, line, n = 0, 0, 1, len(src)
    while i < n:
        if modes and modes[-1] == "tpl":
            start = line
            while i < n:
                c = src[i]
                if c == "\\":
                    line += src.count("\n", i, i + 2)
                    i += 2
                elif c == "`":
                    modes.pop()
                    i += 1
                    toks.append(("str", "`", start))
                    break
                elif src.startswith("${", i):
                    modes.append(("interp", depth))
                    i += 2
                    toks.append(("str", "`", start))
                    break
                else:
                    if c == "\n":
                        line += 1
                    i += 1
            continue
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r\f\v":
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            comments.append((line, src[i:j]))
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            comments.append((line, src[i:j]))
            line += src.count("\n", i, j)
            i = j
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] not in (c, "\n"):
                j += 2 if src[j] == "\\" else 1
            end = j + 1 if j < n and src[j] == c else j
            toks.append(("str", src[i + 1:min(j, n)], line))
            line += src.count("\n", i, end)
            i = end
        elif c == "`":
            modes.append("tpl")
            i += 1
        elif c == "/" and regex_allowed(toks):
            j, in_class = i + 1, False
            while j < n and src[j] != "\n":
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    break
                j += 1
            j = min(j + 1, n)
            while j < n and src[j].isalpha():
                j += 1
            toks.append(("re", src[i:j], line))
            line += src.count("\n", i, j)
            i = j
        elif c == "{":
            depth += 1
            toks.append((P, c, line))
            i += 1
        elif c == "}":
            if modes and modes[-1] != "tpl" and modes[-1][1] == depth:
                modes.pop()
            else:
                depth -= 1
                toks.append((P, c, line))
            i += 1
        else:
            m = IDENT.match(src, i)
            if m:
                toks.append((I, m.group(), line))
                i = m.end()
                continue
            m = NUMBER.match(src, i)
            if m:
                toks.append(("num", m.group(), line))
                i = m.end()
                continue
            toks.append((P, c, line))
            i += 1
    return toks, comments


def regex_allowed(toks):
    if not toks:
        return True
    kind, text, _ = toks[-1]
    if kind == P:
        return text not in (")", "]", "}")
    return kind == I and text in JS_KEYWORDS_BEFORE_EXPR


def at(toks, k, kind, text=None):
    if not 0 <= k < len(toks):
        return False
    return toks[k][0] == kind and (text is None or toks[k][1] == text)


def js_child_calls(toks):
    """Return [(index of the function name, function name)] for each child_process call in the file."""
    bare, modules, calls = {}, set(), []

    def destructure(close):
        k = close
        while k > 0 and not at(toks, k, P, "{"):
            k -= 1
        part = []
        for tok in toks[k + 1:close] + [(P, ",", 0)]:
            if tok[0] == P and tok[1] == ",":
                names = [t[1] for t in part]
                if len(names) == 1 and names[0] in JS_FNS:
                    bare[names[0]] = names[0]
                elif len(names) == 3 and names[1] in (":", "as") and names[0] in JS_FNS:
                    bare[names[2]] = names[0]
                part = []
            else:
                part.append(tok)

    cp_at = [k for k, t in enumerate(toks) if t[0] == "str" and t[1] in CP_NAMES]
    for k in cp_at:
        if at(toks, k - 1, P, "(") and at(toks, k - 2, I, "require"):
            if at(toks, k - 3, P, "="):
                if at(toks, k - 4, P, "}"):
                    destructure(k - 4)
                elif at(toks, k - 4, I):
                    modules.add(toks[k - 4][1])
        elif at(toks, k - 1, I, "from"):
            if at(toks, k - 2, P, "}"):
                destructure(k - 2)
            elif at(toks, k - 2, I):
                modules.add(toks[k - 2][1])
    for k, (kind, text, _) in enumerate(toks):
        if kind != I or not at(toks, k + 1, P, "("):
            continue
        if not at(toks, k - 1, P, "."):
            if text in bare:
                calls.append((k, bare[text]))
        elif text in JS_FNS and at(toks, k - 2, I) and toks[k - 2][1] in modules:
            calls.append((k, text))
    for k in cp_at:
        if (at(toks, k + 1, P, ")") and at(toks, k + 2, P, ".") and at(toks, k + 3, I)
                and toks[k + 3][1] in JS_FNS and at(toks, k + 4, P, "(")):
            calls.append((k + 3, toks[k + 3][1]))
    return calls


def close_of(toks, k):
    """Index of the bracket that closes the opening bracket at k."""
    depth = 0
    for j in range(k, len(toks)):
        kind, text, _ = toks[j]
        if kind != P:
            continue
        if text in ("(", "[", "{"):
            depth += 1
        elif text in (")", "]", "}"):
            depth -= 1
            if depth == 0:
                return j
    return len(toks) - 1


def hides_window(toks, lo, hi):
    return any(at(toks, j, I, "windowsHide") and at(toks, j + 1, P, ":") and at(toks, j + 2, I, "true")
               for j in range(lo, hi))


def js_scan(rel, src):
    """Return (offences, unknown). offences: sorted [(line, text)]. src is bytes."""
    try:
        toks, comments = lex_js(src.decode("utf-8"))
    except UnicodeDecodeError as e:
        return [], "UNKNOWN %s: %s" % (rel, e)
    ok_lines = marker_lines(comments)
    out = []
    for k, fn in js_child_calls(toks):
        line = toks[k][2]
        if hides_window(toks, k + 2, close_of(toks, k + 1)) or excused(ok_lines, line):
            continue
        out.append((line, "child_process.%s without windowsHide: true" % fn))
    return sorted(out), None


def scan_repo(root=ROOT):
    """Return (scanned, found, unknown): product files read, {rel: offences}, and read failures."""
    def head(rel):
        with open(os.path.join(root, rel), "rb") as f:
            return f.read(200)
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    scanned, found, unknown = [], {}, []
    for rel in listed.decode("utf-8").split("\0"):
        kind = product_kind(rel, head) if rel else None
        if kind is None:
            continue
        scanned.append(rel)
        with open(os.path.join(root, rel), "rb") as f:
            src = f.read()
        hits, err = (py_scan if kind == "py" else js_scan)(rel, src)
        if err:
            unknown.append(err)
        elif hits:
            found[rel] = hits
    return scanned, found, unknown


def report(found):
    per_dir, per_file = {}, []
    for rel, hits in found.items():
        top = rel.split("/", 1)[0]
        per_dir[top] = per_dir.get(top, 0) + len(hits)
        per_file.append((len(hits), rel))
    lines = ["%d offending call sites in %d files" % (sum(per_dir.values()), len(found)), "per directory:"]
    lines += ["  %-12s %4d" % (d, c) for d, c in sorted(per_dir.items(), key=lambda kv: (-kv[1], kv[0]))]
    lines.append("per file, most first:")
    lines += ["  %4d  %s" % (c, rel) for c, rel in sorted(per_file, key=lambda x: (-x[0], x[1]))]
    lines.append("each offence:")
    for rel in sorted(found):
        lines += ["  %s:%d: %s" % (rel, line, text) for line, text in found[rel]]
    return "\n".join(lines)


def py_hits(src, rel="hooks/fixture.py"):
    hits, err = py_scan(rel, src.encode("utf-8"))
    if err:
        raise AssertionError(err)
    return hits


def js_hits(src, rel="mods/fixture/hook.mjs"):
    hits, err = js_scan(rel, src.encode("utf-8"))
    if err:
        raise AssertionError(err)
    return hits


IMPORT_EXEC = 'import { execSync } from "node:child_process";\n'


class PythonFixtures(unittest.TestCase):
    def test_raw_call_is_offence(self):
        self.assertEqual(py_hits("import subprocess\nsubprocess.run(['x'])\n"), [(2, "subprocess.run outside the no-window helper")])

    def test_creationflags_alone_is_still_offence(self):
        self.assertEqual(len(py_hits("import subprocess\nsubprocess.run(['x'], creationflags=0x08000000)\n")), 1)

    def test_helper_route_is_clean(self):
        self.assertEqual(py_hits("from hooks import _nowindow\n_nowindow.run(['x'])\n"), [])

    def test_module_alias_is_offence(self):
        self.assertEqual(len(py_hits("import subprocess as sp\nsp.Popen(['x'])\n")), 1)

    def test_from_import_alias_is_offence(self):
        self.assertEqual(len(py_hits("from subprocess import check_output as co\nco(['x'])\n")), 1)

    def test_lazy_import_inside_function_is_offence(self):
        self.assertEqual(len(py_hits("def f():\n    import subprocess\n    subprocess.check_call(['x'])\n")), 1)

    def test_names_that_are_not_spawns_are_clean(self):
        self.assertEqual(py_hits("import subprocess\nx = subprocess.DEVNULL\nraise subprocess.TimeoutExpired('x', 1)\n"), [])

    def test_other_objects_run_method_is_clean(self):
        self.assertEqual(py_hits("class R:\n    def run(self):\n        pass\nR().run()\nrunner.run(['x'])\n"), [])

    def test_marker_with_reason_on_line_above_excuses(self):
        self.assertEqual(py_hits("import subprocess\n# nowindow: needs a console (interactive)\nsubprocess.call(['x'])\n"), [])

    def test_marker_on_call_line_excuses(self):
        self.assertEqual(py_hits("import subprocess\nsubprocess.call(['x'])  # nowindow: needs a console\n"), [])

    def test_marker_without_reason_excuses_nothing(self):
        self.assertEqual(len(py_hits("import subprocess\n# nowindow:\nsubprocess.call(['x'])\n")), 1)

    def test_marker_inside_string_excuses_nothing(self):
        self.assertEqual(len(py_hits('import subprocess\nnote = "# nowindow: fake reason"\nsubprocess.call(["x"])\n')), 1)

    def test_comment_openers_inside_string_do_not_hide_the_defect(self):
        src = 'import subprocess\nurl = "http://a.test/#frag"; s = "# not a comment"; t = "/* not a comment"\nsubprocess.call(["x"])\n'
        self.assertEqual([line for line, _ in py_hits(src)], [3])

    def test_multiline_string_holding_a_call_is_clean(self):
        self.assertEqual(py_hits('import subprocess\nDOC = """\nsubprocess.run(["x"])\n"""\n'), [])

    def test_lone_quote_in_text_does_not_hide_the_defect(self):
        self.assertEqual([line for line, _ in py_hits("import subprocess\nnote = \"Don't\"\nsubprocess.run(['x'])\n")], [3])

    def test_helper_file_itself_is_exempt(self):
        hits, err = py_scan(HELPER, b"import subprocess\nsubprocess.run(['x'])\n")
        self.assertEqual((hits, err), ([], None))

    def test_unparseable_file_is_unknown_not_clean(self):
        hits, err = py_scan("hooks/broken.py", b"def (:\n")
        self.assertIsNotNone(err)
        self.assertTrue(err.startswith("UNKNOWN hooks/broken.py"))


class JavaScriptFixtures(unittest.TestCase):
    def test_unhidden_call_is_offence(self):
        self.assertEqual(js_hits(IMPORT_EXEC + 'execSync("x");\n'), [(2, "child_process.execSync without windowsHide: true")])

    def test_inline_windows_hide_is_clean(self):
        self.assertEqual(js_hits(IMPORT_EXEC + 'execSync("x", { windowsHide: true });\n'), [])

    def test_windows_hide_false_is_offence(self):
        self.assertEqual(len(js_hits(IMPORT_EXEC + 'execSync("x", { windowsHide: false });\n')), 1)

    def test_options_held_in_a_variable_is_offence(self):
        self.assertEqual(len(js_hits(IMPORT_EXEC + 'const o = { windowsHide: true };\nexecSync("x", o);\n')), 1)

    def test_renamed_import_is_offence(self):
        self.assertEqual(len(js_hits('import { exec as run } from "node:child_process";\nrun("x");\n')), 1)

    def test_namespace_import_member_calls(self):
        src = 'import * as cp from "node:child_process";\ncp.spawnSync("x", [], { windowsHide: true });\ncp.spawnSync("y");\n'
        self.assertEqual([line for line, _ in js_hits(src)], [3])

    def test_require_destructure_is_offence(self):
        self.assertEqual(len(js_hits('const { spawn } = require("child_process");\nspawn("x");\n')), 1)

    def test_require_member_call_is_offence(self):
        self.assertEqual(len(js_hits('require("node:child_process").execFileSync("x");\n')), 1)

    def test_local_exec_without_child_process_import_is_clean(self):
        self.assertEqual(js_hits('function exec(c) { return c; }\nexec("x");\n'), [])

    def test_regex_exec_is_clean(self):
        src = 'import { spawnSync } from "node:child_process";\nconst m = /x/.exec(s);\nspawnSync("x", { windowsHide: true });\n'
        self.assertEqual(js_hits(src), [])

    def test_marker_line_above_excuses(self):
        self.assertEqual(js_hits(IMPORT_EXEC + "// nowindow: needs a console (interactive)\nexecSync(\"x\");\n"), [])

    def test_block_marker_excuses(self):
        self.assertEqual(js_hits(IMPORT_EXEC + "/* nowindow: needs a console */\nexecSync(\"x\");\n"), [])

    def test_marker_without_reason_excuses_nothing(self):
        self.assertEqual(len(js_hits(IMPORT_EXEC + "// nowindow:\nexecSync(\"x\");\n")), 1)

    def test_marker_inside_string_excuses_nothing(self):
        self.assertEqual([line for line, _ in js_hits(IMPORT_EXEC + 'const s = "// nowindow: fake reason";\nexecSync("x");\n')], [3])

    def test_line_comment_opener_in_string_then_defect(self):
        self.assertEqual([line for line, _ in js_hits(IMPORT_EXEC + 'const u = "http://a.test/"; execSync("x");\n')], [2])

    def test_block_comment_opener_in_string_then_defect(self):
        self.assertEqual([line for line, _ in js_hits(IMPORT_EXEC + 'const s = "/* not a comment"; execSync("x");\n')], [2])

    def test_hash_in_string_then_defect(self):
        self.assertEqual([line for line, _ in js_hits(IMPORT_EXEC + 'const h = "# not a comment"; execSync("x");\n')], [2])

    def test_multiline_template_holding_a_call_is_clean_but_the_real_call_is_flagged(self):
        src = (IMPORT_EXEC + "const t = `first line\nexecSync(\"x\", { windowsHide: true })\nlast line`;\n"
               + 'execSync("y");\n')
        self.assertEqual([line for line, _ in js_hits(src)], [5])

    def test_template_interpolation_with_braces_and_quotes(self):
        src = IMPORT_EXEC + 'const t = `a ${ "}" } b`;\nexecSync("y", { windowsHide: true });\n'
        self.assertEqual(js_hits(src), [])

    def test_lone_quote_in_string_does_not_hide_the_defect(self):
        self.assertEqual([line for line, _ in js_hits(IMPORT_EXEC + 'const q = "<p>Don\'t</p>";\nexecSync("x");\n')], [3])

    def test_lone_quote_in_comment_does_not_hide_the_defect(self):
        self.assertEqual([line for line, _ in js_hits(IMPORT_EXEC + "// Don't do this\nexecSync(\"x\");\n")], [3])

    def test_regex_literal_holding_a_quote_does_not_hide_the_defect(self):
        self.assertEqual([line for line, _ in js_hits(IMPORT_EXEC + 'const r = /"/;\nexecSync("x");\n')], [3])


class ProductFileKinds(unittest.TestCase):
    def head(self, first):
        return lambda rel: first

    def test_test_files_are_not_product(self):
        for rel in ("hooks/test_guard.py", "hooks/case_runner_test.py", "lint/conftest.py",
                    "actions/stamp/test_stamp.mjs", "mods/decision-watch/decision-watch.test.mjs"):
            with self.subTest(rel=rel):
                self.assertIsNone(product_kind(rel, self.head(b"")))

    def test_product_kinds(self):
        self.assertEqual(product_kind("hooks/guard.py", self.head(b"")), "py")
        self.assertEqual(product_kind("mods/session-board/hooks/receiver-state.mjs", self.head(b"")), "js")
        self.assertEqual(product_kind("actions/stamp/stamp.mjs", self.head(b"")), "js")

    def test_extensionless_python_by_shebang_only(self):
        self.assertEqual(product_kind("bin/verdict", self.head(b"#!/usr/bin/env python3\n")), "py")
        self.assertIsNone(product_kind("bin/rm", self.head(b"#!/bin/sh\n")))
        self.assertIsNone(product_kind("skills/impeccable/scripts/impeccable", self.head(b"#!/bin/sh\n")))

    def test_js_outside_mods_and_actions_is_not_product(self):
        self.assertIsNone(product_kind("skills/impeccable/scripts/live-browser.js", self.head(b"")))


class RepoScan(unittest.TestCase):
    def test_product_files_start_no_console_window(self):
        scanned, found, unknown = scan_repo()
        for rel in ("hooks/guard.py", "bin/verdict", "actions/stamp/stamp.mjs",
                    "mods/session-board/hooks/receiver-state.mjs"):
            self.assertIn(rel, scanned, "scan did not read %s" % rel)
        self.assertNotIn("hooks/test_guard.py", scanned)
        self.assertEqual(unknown, [], "files the scan could not read: " + "; ".join(unknown))
        self.assertEqual(found, {}, report(found))


if __name__ == "__main__":
    unittest.main()
