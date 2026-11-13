# section 42841
FAMILY = "builder-refuse"
# A builder may change a test file when the change is comments only. The guard proves it with the language's
# own tokenizer (Python) or parser (JS and TS): the code tokens of the old text and the new text match. Every
# other change to a test path stays refused, and so does a change the guard cannot prove: an unknown language,
# an unparsable file, a new file, a deleted file.
#
# Each change is one edit to one file of TC_FILES, the base every fixture here shares. `_tc_edit` fails the
# run when its anchor is not in the base exactly once, so no case passes on a change that did not happen.

TC_BUILDER = dict(agent_id="bld1", agent_type="builder")
# The rule the write tool and the shell check print. The commit, push and stop check prints BDIFF.
TC_RULE = "builder-test-edit"


def _tc_edit(text, old, new):
    """`text` with `old` replaced by `new`. `old` must occur in `text` exactly once."""
    found = text.count(old)
    if found != 1:
        sys.exit("fixture setup failed: %r occurs %d times in the base text, want once" % (old, found))
    return text.replace(old, new)


def _tc_fixture(name, change, committed=False):
    """A fixture repo over TC_FILES, with `change` applied to its worktree. `committed` commits the change
    there, as a builder's push sees it; otherwise the change is still uncommitted, as a commit or stop sees it."""
    return diff_repo("tc-%s%s" % (name, "-committed" if committed else ""), change,
                     commit=committed, files=TC_FILES)


def _tc_change(name, rel, text, committed=False):
    return _tc_fixture(name, _put(rel, text), committed)


# Python. The base holds a comment above the function, a comment inside it, a docstring and a trailing comment.
TC_PY = "tests/test_tc_py.py"
TC_PY_BASE = (
    "# A note on the module.\n"
    "import os  # why it is here\n"
    "\n"
    "def test_tc():\n"
    "    \"\"\"Docstring one.\"\"\"\n"
    "    # inside note\n"
    "    assert os.sep  # keep\n"
)
TC_PY_ADDED = _tc_edit(TC_PY_BASE, "def test_tc():", "# builder note\ndef test_tc():")
TC_PY_EDITED = _tc_edit(TC_PY_BASE, "# A note on the module.", "# A changed note on the module.")
TC_PY_REMOVED = _tc_edit(TC_PY_BASE, "    # inside note\n", "")
TC_PY_TRAILING = _tc_edit(TC_PY_BASE, "def test_tc():", "def test_tc():  # the one test")

# A `#` inside a string: a naive comment cut would see `#b"` and `#c"` as the same comment and allow the change.
TC_STR = "tests/test_tc_str.py"
TC_STR_BASE = 'TOKEN = "a#b"\n'
# A comment opener inside a multi-line string: a line cut would read `# one` as a comment.
TC_MLINE = "tests/test_tc_mline.py"
TC_MLINE_BASE = 'DOC = """\n# one\n"""\n'
# Code written as a comment: `# assert` uncommented is a new assert.
TC_DISGUISE = "tests/test_tc_disguise.py"
TC_DISGUISE_BASE = "import os\n# assert os.sep == '/'\n"
# A test file the tokenizer cannot read: an unterminated triple-quoted string.
TC_BROKEN_PY = "tests/test_tc_broken.py"
TC_BROKEN_PY_BASE = 'x = 1\n# note\ns = """open\n'
# A committed test file that a case deletes.
TC_GONE = "tests/test_tc_gone.py"
TC_GONE_BASE = "# only a note\n"
# An existing empty test file: it gains a comment, and it is not a new file.
TC_EMPTY = "tests/test_tc_empty.py"
TC_EMPTY_BASE = ""
TC_NEW = "tests/test_tc_new.py"
TC_NEW_EMPTY = "tests/test_tc_new_empty.py"

# JavaScript and TSX. The TypeScript parser reads them; a template literal holds a comment opener.
TC_JS = "web/app.test.js"
TC_JS_BASE = "// Old note.\nconst total = 1; // count\n/* block note */\nexport const ok = total === 1;\n"
TC_TPL = "web/tpl.test.js"
TC_TPL_BASE = "const t = `line one\n// not a comment\nline three`;\n"
# A lone quote in JSX text: a scanner that reads the quote as a string start would hide what follows it.
TC_JSX = "web/jsx.test.tsx"
TC_JSX_BASE = "export const a = <p>Don't</p>;\n"
TC_JS_UNCOMMENT = "web/uncomment.test.js"
TC_JS_UNCOMMENT_BASE = "// assert(total === 2);\nexport const b = 1;\n"
TC_JS_SLASH = "web/slash.test.js"
TC_JS_SLASH_BASE = "const a = 1; // b = 2;\n"
TC_JS_BROKEN = "web/broken.test.js"
TC_JS_BROKEN_BASE = "function f( {\n// note\n"

# A language the guard has no tokenizer for, a mutation test, and test config.
TC_RB = "test/user_test.rb"
TC_RB_BASE = "# user note\nputs 1\n"
TC_MUT = "hooks/mutate_guard.py"
TC_MUT_BASE = "# mutant note\nx = 1\n"
TC_INI = "pytest.ini"
TC_INI_BASE = "[pytest]\n# note\naddopts = -q\n"

# A block comment that holds a line break after `return`: the break ends the statement (automatic semicolon
# insertion), so the collapsed form is code, not a comment.
TC_ASI = "web/asi.test.js"
TC_ASI_BASE = "export function f(x) {\n  return /* c\n */ x;\n}\n"
# A regex literal holds `//`, which a line cut would read as a comment opener.
TC_RE = "web/regex.test.js"
TC_RE_BASE = (r"const r = /a\/\/b/;" "\n" r"const u = /https?:\/\//;" "\n" "// note\n"
              'export const ok = r.test("a//b") && u.test("http://");\n')
# A coding cookie (PEP 263) is read from line 1 or 2, so a change to its text is no comment change.
TC_COOKIE = "tests/test_tc_cookie.py"
TC_COOKIE_BASE = "# -*- coding: utf-8 -*-\nx = 1  # keep\n"
# The smallest file a cookie sits in: the cookie and nothing else.
TC_COOKIE_ONLY = "tests/test_tc_cookie_only.py"
TC_COOKIE_ONLY_BASE = "# -*- coding: utf-8 -*-\n"

TC_FILES = {
    **BASE_FILES,
    TC_PY: TC_PY_BASE, TC_STR: TC_STR_BASE, TC_MLINE: TC_MLINE_BASE, TC_DISGUISE: TC_DISGUISE_BASE,
    TC_BROKEN_PY: TC_BROKEN_PY_BASE, TC_GONE: TC_GONE_BASE, TC_EMPTY: TC_EMPTY_BASE,
    TC_JS: TC_JS_BASE, TC_TPL: TC_TPL_BASE, TC_JSX: TC_JSX_BASE, TC_JS_UNCOMMENT: TC_JS_UNCOMMENT_BASE,
    TC_JS_SLASH: TC_JS_SLASH_BASE, TC_JS_BROKEN: TC_JS_BROKEN_BASE,
    TC_RB: TC_RB_BASE, TC_MUT: TC_MUT_BASE, TC_INI: TC_INI_BASE,
    TC_ASI: TC_ASI_BASE, TC_RE: TC_RE_BASE, TC_COOKIE: TC_COOKIE_BASE, TC_COOKIE_ONLY: TC_COOKIE_ONLY_BASE,
}

# The write tool judges the file on disk, with the edit applied, so its cases share one clean checkout.
_tc_base_repo = _tc_fixture("base", lambda w: None)


# GREEN. Python comments added, edited, removed and added after code: allowed at commit, push and stop.
for _tc_label, _tc_text in (("added", TC_PY_ADDED), ("edited", TC_PY_EDITED),
                            ("removed", TC_PY_REMOVED), ("trailing", TC_PY_TRAILING)):
    _tc_uncommitted = _tc_change("py-%s" % _tc_label, TC_PY, _tc_text)
    _tc_committed = _tc_change("py-%s" % _tc_label, TC_PY, _tc_text, committed=True)
    sh("builder-refuse: a python comment %s in a test file is allowed at commit" % _tc_label,
       COMMIT, "allow", cwd=_tc_uncommitted, **TC_BUILDER)
    sh("builder-refuse: a python comment %s in a test file is allowed at push" % _tc_label,
       PUSH, "allow", cwd=_tc_committed, **TC_BUILDER)
    add("builder-refuse: a python comment %s in a test file is allowed at the first stop" % _tc_label,
        "allow", event="SubagentStop", cwd=_tc_uncommitted, **TC_BUILDER)

# GREEN. The write tool by path: an Edit that adds, edits or removes a comment, and a Write of the whole file
# with one comment added, are allowed.
add("builder-refuse: a python comment edited by the Edit tool is allowed", "allow", tool="Edit",
    file_path=TC_PY, old_string="# A note on the module.", new_string="# A changed note on the module.",
    cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: a python comment added by the Edit tool is allowed", "allow", tool="Edit",
    file_path=TC_PY, old_string="def test_tc():", new_string="# builder note\ndef test_tc():",
    cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: a python comment removed by the Edit tool is allowed", "allow", tool="Edit",
    file_path=TC_PY, old_string="    # inside note\n", new_string="", cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: a python test file rewritten by the Write tool with one comment added is allowed",
    "allow", tool="Write", file_path=TC_PY, content=TC_PY_ADDED, cwd=_tc_base_repo, **TC_BUILDER)

# GREEN. An existing empty test file gains a comment: only comments change, and the file is not new.
_tc_empty = _tc_change("empty-gains-comment", TC_EMPTY, "# a note\n")
sh("builder-refuse: a comment added to an existing empty test file is allowed at commit",
   COMMIT, "allow", cwd=_tc_empty, **TC_BUILDER)

# GREEN. JavaScript: a `//` comment, a `/* */` comment and a trailing comment, at commit and push; then the Edit tool.
for _tc_label, _tc_text in (
        ("line comment", _tc_edit(TC_JS_BASE, "// Old note.", "// New note.")),
        ("block comment", _tc_edit(TC_JS_BASE, "/* block note */", "/* block edit */")),
        ("trailing comment", _tc_edit(TC_JS_BASE, "export const ok = total === 1;",
                                      "export const ok = total === 1; // checked"))):
    _tc_uncommitted = _tc_change("js-%s" % _tc_label.replace(" ", "-"), TC_JS, _tc_text)
    _tc_committed = _tc_change("js-%s" % _tc_label.replace(" ", "-"), TC_JS, _tc_text, committed=True)
    sh("builder-refuse: a javascript %s edit in a test file is allowed at commit" % _tc_label,
       COMMIT, "allow", cwd=_tc_uncommitted, **TC_BUILDER)
    sh("builder-refuse: a javascript %s edit in a test file is allowed at push" % _tc_label,
       PUSH, "allow", cwd=_tc_committed, **TC_BUILDER)
add("builder-refuse: a javascript line comment edited by the Edit tool is allowed", "allow", tool="Edit",
    file_path=TC_JS, old_string="// Old note.", new_string="// New note.", cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: a javascript block comment edited by the Edit tool is allowed", "allow", tool="Edit",
    file_path=TC_JS, old_string="/* block note */", new_string="/* block edit */", cwd=_tc_base_repo, **TC_BUILDER)

# GREEN control for the lone quote: a comment added above JSX text that holds `Don't` is still a comment change.
_tc_jsx_control = _tc_change("jsx-comment-above", TC_JSX, "// note\n" + TC_JSX_BASE)
sh("builder-refuse: a comment added above JSX text with a lone quote is allowed at commit",
   COMMIT, "allow", cwd=_tc_jsx_control, **TC_BUILDER)

# GREEN control for the write tool on test config: a comment with no test-disabling text is still allowed.
_tc_ini_note = _tc_change("ini-note", TC_INI, _tc_edit(TC_INI_BASE, "# note", "# note two"))
sh("builder-refuse: a comment-only edit of pytest.ini with no test-disabling line is allowed at commit",
   COMMIT, "allow", cwd=_tc_ini_note, **TC_BUILDER)
add("builder-refuse: a comment-only edit of pytest.ini with no test-disabling line is allowed by the Edit tool",
    "allow", tool="Edit", file_path=TC_INI, old_string="# note", new_string="# note two",
    cwd=_tc_base_repo, **TC_BUILDER)


# RED. Each of these is refused today and must stay refused. A green here means a comment-only check let
# through a change that is not a comment.

# A code change: refused at commit, push and stop.
_tc_code = _tc_change("py-code", TC_PY, _tc_edit(TC_PY_BASE, "assert os.sep  # keep",
                                                 "assert not os.sep  # keep"))
_tc_code_pushed = _tc_change("py-code", TC_PY, _tc_edit(TC_PY_BASE, "assert os.sep  # keep",
                                                        "assert not os.sep  # keep"), committed=True)
sh("builder-refuse: a python code change in a test file is denied at commit", COMMIT, "deny", rule=BDIFF,
   cwd=_tc_code, **TC_BUILDER)
sh("builder-refuse: a python code change in a test file is denied at push", PUSH, "deny", rule=BDIFF,
   cwd=_tc_code_pushed, **TC_BUILDER)
add("builder-refuse: a python code change in a test file is denied at the first stop", "deny", rule=BDIFF,
    event="SubagentStop", cwd=_tc_code, **TC_BUILDER)

# A changed docstring is code, not a comment.
_tc_doc = _tc_change("py-docstring", TC_PY, _tc_edit(TC_PY_BASE, "Docstring one.", "Docstring two."))
_tc_doc_pushed = _tc_change("py-docstring", TC_PY, _tc_edit(TC_PY_BASE, "Docstring one.", "Docstring two."),
                            committed=True)
sh("builder-refuse: a changed python docstring is denied at commit", COMMIT, "deny", rule=BDIFF,
   cwd=_tc_doc, **TC_BUILDER)
sh("builder-refuse: a changed python docstring is denied at push", PUSH, "deny", rule=BDIFF,
   cwd=_tc_doc_pushed, **TC_BUILDER)
add("builder-refuse: a changed python docstring is denied by the Edit tool", "deny", rule=TC_RULE,
    tool="Edit", file_path=TC_PY, old_string="Docstring one.", new_string="Docstring two.",
    cwd=_tc_base_repo, **TC_BUILDER)

# A `#` inside a string, turned from string text into other string text.
sh("builder-refuse: a `#` inside a python string changed to other string text is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_tc_change("py-string-hash", TC_STR, _tc_edit(TC_STR_BASE, "a#b", "a#c")),
   **TC_BUILDER)
add("builder-refuse: a `#` inside a python string changed to other string text is denied by the Edit tool",
    "deny", rule=TC_RULE, tool="Edit", file_path=TC_STR, old_string="a#b", new_string="a#c",
    cwd=_tc_base_repo, **TC_BUILDER)

# A comment opener inside a multi-line python string.
sh("builder-refuse: a comment opener inside a multi-line python string changed is denied at commit",
   COMMIT, "deny", rule=BDIFF,
   cwd=_tc_change("py-multiline-hash", TC_MLINE, _tc_edit(TC_MLINE_BASE, "# one", "# two")), **TC_BUILDER)

# Code written as a comment, uncommented.
sh("builder-refuse: a python assert uncommented from a comment is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("py-uncomment", TC_DISGUISE,
                              _tc_edit(TC_DISGUISE_BASE, "# assert os.sep == '/'", "assert os.sep == '/'")),
   **TC_BUILDER)

# A new test file holding only comments, and an empty new test file: a new file is refused.
sh("builder-refuse: a new python test file holding only a comment is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("py-new-comment-only", TC_NEW, "# only a note\n"), **TC_BUILDER)
add("builder-refuse: a new python test file holding only a comment is denied by the Write tool", "deny",
    rule=TC_RULE, tool="Write", file_path=TC_NEW, content="# only a note\n", cwd=_tc_base_repo, **TC_BUILDER)
sh("builder-refuse: a new empty python test file is denied at commit", COMMIT, "deny", rule=BDIFF,
   cwd=_tc_change("py-new-empty", TC_NEW_EMPTY, ""), **TC_BUILDER)

# A deleted test file, even one that held only a comment.
_tc_gone = _tc_fixture("gone", _rm(TC_GONE))
_tc_gone_pushed = _tc_fixture("gone", _rm(TC_GONE), committed=True)
sh("builder-refuse: a deleted test file that held only a comment is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_gone, **TC_BUILDER)
sh("builder-refuse: a deleted test file that held only a comment is denied at push", PUSH, "deny",
   rule=BDIFF, cwd=_tc_gone_pushed, **TC_BUILDER)

# A python test file the tokenizer cannot read: a comment edit is not provable.
sh("builder-refuse: a comment edit in an unparsable python test file is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("py-unparsable", TC_BROKEN_PY, _tc_edit(TC_BROKEN_PY_BASE, "# note", "# changed")),
   **TC_BUILDER)

# A language the guard has no tokenizer for: a comment edit is refused, at commit and by the Edit tool.
sh("builder-refuse: a comment edit in a ruby test file is denied at commit", COMMIT, "deny", rule=BDIFF,
   cwd=_tc_change("rb-comment", TC_RB, _tc_edit(TC_RB_BASE, "# user note", "# user note, reworded")),
   **TC_BUILDER)
add("builder-refuse: a comment edit in a ruby test file is denied by the Edit tool", "deny", rule=TC_RULE,
    tool="Edit", file_path=TC_RB, old_string="# user note", new_string="# user note, reworded",
    cwd=_tc_base_repo, **TC_BUILDER)

# The mutation tests keep their old rule: a builder never changes them, comments or not.
sh("builder-refuse: a comment edit in a mutation test is denied at commit", COMMIT, "deny", rule=BDIFF,
   cwd=_tc_change("mutation-comment", TC_MUT, _tc_edit(TC_MUT_BASE, "# mutant note", "# mutant note, reworded")),
   **TC_BUILDER)
add("builder-refuse: a comment edit in a mutation test is denied by the Edit tool", "deny", rule=TC_RULE,
    tool="Edit", file_path=TC_MUT, old_string="# mutant note", new_string="# mutant note, reworded",
    cwd=_tc_base_repo, **TC_BUILDER)

# Test config keeps its old rule: a comment that adds a test-disabling line is still refused.
_tc_ini_disable = "# note\n# addopts = --deselect tests/test_tc_py.py"
sh("builder-refuse: a comment in pytest.ini that adds a test-disabling flag is denied at commit", COMMIT,
   "deny", rule=BDIFF, cwd=_tc_change("ini-disabling-comment", TC_INI, _tc_edit(TC_INI_BASE, "# note",
                                                                              _tc_ini_disable)),
   **TC_BUILDER)
add("builder-refuse: a comment in pytest.ini that adds a test-disabling flag is denied by the Edit tool",
    "deny", rule=TC_RULE, tool="Edit", file_path=TC_INI, old_string="# note", new_string=_tc_ini_disable,
    cwd=_tc_base_repo, **TC_BUILDER)

# An Edit whose old text is not in the file: the result is not provable, so it is refused.
add("builder-refuse: an Edit whose old text is not in the test file is denied by the Edit tool", "deny",
    rule=TC_RULE, tool="Edit", file_path=TC_PY, old_string="# nonexistent note", new_string="# x",
    cwd=_tc_base_repo, **TC_BUILDER)

# JavaScript. A comment opener inside a multi-line template literal is string text.
sh("builder-refuse: a comment opener inside a multi-line javascript template literal changed is denied at commit",
   COMMIT, "deny", rule=BDIFF,
   cwd=_tc_change("js-template", TC_TPL, _tc_edit(TC_TPL_BASE, "// not a comment", "// changed text")),
   **TC_BUILDER)

# A lone quote in JSX text: `Don't` changed to `Do` is a code change.
sh("builder-refuse: JSX text `Don't` changed to `Do` in a test file is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("jsx-lone-quote", TC_JSX, _tc_edit(TC_JSX_BASE, "<p>Don't</p>", "<p>Do</p>")),
   **TC_BUILDER)

# Code written as a comment, and a `//` removed from a code line.
sh("builder-refuse: a javascript assert uncommented from a `//` comment is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("js-uncomment", TC_JS_UNCOMMENT,
                              _tc_edit(TC_JS_UNCOMMENT_BASE, "// assert(total === 2);", "assert(total === 2);")),
   **TC_BUILDER)
sh("builder-refuse: a `//` removed from a javascript code line is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("js-slash", TC_JS_SLASH, _tc_edit(TC_JS_SLASH_BASE, "// b = 2;", "b = 2;")),
   **TC_BUILDER)

# A javascript test file that does not parse: a comment edit is not provable.
sh("builder-refuse: a comment edit in an unparsable javascript test file is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("js-unparsable", TC_JS_BROKEN, _tc_edit(TC_JS_BROKEN_BASE, "// note", "// changed")),
   **TC_BUILDER)


# A line break inside a block comment after `return` ends the statement, so the collapsed form changes the code.
sh("builder-refuse: a javascript block comment holding a line break, collapsed onto one line after return, is denied at commit",
   COMMIT, "deny", rule=BDIFF,
   cwd=_tc_change("js-asi-collapsed", TC_ASI, _tc_edit(TC_ASI_BASE, "/* c\n */ x;", "/* c */ x;")), **TC_BUILDER)
add("builder-refuse: a javascript block comment holding a line break, collapsed onto one line after return, is denied by the Edit tool",
    "deny", rule=TC_RULE, tool="Edit", file_path=TC_ASI, old_string="/* c\n */ x;", new_string="/* c */ x;",
    cwd=_tc_base_repo, **TC_BUILDER)
# GREEN control: the same block comment with its line break kept and only its text changed is a comment change.
sh("builder-refuse: a javascript block comment holding a line break, with its text changed and the break kept, is allowed at commit",
   COMMIT, "allow", cwd=_tc_change("js-asi-kept", TC_ASI, _tc_edit(TC_ASI_BASE, "/* c\n", "/* d\n")), **TC_BUILDER)

# A `//` inside a regex literal is regex text. Changing it is a code change, though a line cut would read
# `//b/;` as a comment.
sh("builder-refuse: a regex literal holding // changed inside the regex is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("js-regex-slashes", TC_RE, _tc_edit(TC_RE_BASE, r"/a\/\/b/", r"/a\/\/c/")),
   **TC_BUILDER)
sh("builder-refuse: a regex literal holding https?:// changed inside the regex is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("js-regex-url", TC_RE, _tc_edit(TC_RE_BASE, r"/https?:\/\//", r"/http:\/\//")),
   **TC_BUILDER)
add("builder-refuse: a regex literal holding // changed inside the regex is denied by the Edit tool", "deny",
    rule=TC_RULE, tool="Edit", file_path=TC_RE, old_string=r"/a\/\/b/", new_string=r"/a\/\/c/",
    cwd=_tc_base_repo, **TC_BUILDER)
# GREEN control: a comment edited next to the regex literal is a comment change.
sh("builder-refuse: a comment edited next to a regex literal holding // is allowed at commit", COMMIT, "allow",
   cwd=_tc_change("js-regex-comment", TC_RE, _tc_edit(TC_RE_BASE, "// note", "// note, reworded")), **TC_BUILDER)

# A coding cookie on line 1 is read by the interpreter. A comment above it, or between it and the code, moves
# no code. A change to the cookie's text, or its removal, changes how the file is read, so it stays refused.
sh("builder-refuse: a python comment added on line 2, under the coding cookie, is allowed at commit", COMMIT,
   "allow", cwd=_tc_change("cookie-note-line-2", TC_COOKIE,
                           _tc_edit(TC_COOKIE_BASE, "x = 1  # keep", "# note\nx = 1  # keep")), **TC_BUILDER)
sh("builder-refuse: a python comment added after the code, under the coding cookie, is allowed at commit", COMMIT,
   "allow", cwd=_tc_change("cookie-note-after-code", TC_COOKIE,
                           _tc_edit(TC_COOKIE_BASE, "x = 1  # keep\n", "x = 1  # keep\n# note\n")), **TC_BUILDER)
sh("builder-refuse: a python comment added above the coding cookie is allowed at commit", COMMIT, "allow",
   cwd=_tc_change("cookie-note-above", TC_COOKIE,
                  _tc_edit(TC_COOKIE_BASE, "# -*- coding: utf-8 -*-", "# note\n# -*- coding: utf-8 -*-")), **TC_BUILDER)
sh("builder-refuse: a python comment added to a file that holds only the coding cookie is allowed at commit", COMMIT,
   "allow", cwd=_tc_change("cookie-only-note", TC_COOKIE_ONLY,
                           _tc_edit(TC_COOKIE_ONLY_BASE, "# -*- coding: utf-8 -*-\n",
                                    "# -*- coding: utf-8 -*-\n# note\n")), **TC_BUILDER)
sh("builder-refuse: a python coding cookie whose encoding is changed is denied at commit", COMMIT, "deny",
   rule=BDIFF, cwd=_tc_change("cookie-encoding", TC_COOKIE, _tc_edit(TC_COOKIE_BASE, "utf-8", "latin-1")),
   **TC_BUILDER)
sh("builder-refuse: a python coding cookie line that is deleted is denied at commit", COMMIT, "deny", rule=BDIFF,
   cwd=_tc_change("cookie-deleted", TC_COOKIE, _tc_edit(TC_COOKIE_BASE, "# -*- coding: utf-8 -*-\n", "")),
   **TC_BUILDER)
add("builder-refuse: a python comment added on line 2, under the coding cookie, is allowed by the Edit tool", "allow",
    tool="Edit", file_path=TC_COOKIE, old_string="x = 1  # keep", new_string="# note\nx = 1  # keep",
    cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: a python comment added above the coding cookie is allowed by the Edit tool", "allow",
    tool="Edit", file_path=TC_COOKIE, old_string="# -*- coding: utf-8 -*-", new_string="# note\n# -*- coding: utf-8 -*-",
    cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: a python coding cookie whose encoding is changed is denied by the Edit tool", "deny",
    rule=TC_RULE, tool="Edit", file_path=TC_COOKIE, old_string="utf-8", new_string="latin-1",
    cwd=_tc_base_repo, **TC_BUILDER)

# A write call that holds both shapes is refused. The guard replays the comment edit, and the tool may write the
# code in `content` instead.
add("builder-refuse: a Write with a comment edit and a code content is denied by the Write tool", "deny",
    rule=TC_RULE, tool="Write", file_path=TC_PY, content="assert 2", old_string="# A note on the module.",
    new_string="# A changed note on the module.", cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: a Write with an edits list of a comment edit and a code content is denied by the Write tool",
    "deny", rule=TC_RULE, tool="Write", file_path=TC_PY, content="assert 2",
    edits=[{"old_string": "# A note on the module.", "new_string": "# A changed note on the module."}],
    cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: an Edit with an edits list of a comment edit and a code content is denied by the Edit tool",
    "deny", rule=TC_RULE, tool="Edit", file_path=TC_PY, content="assert 2",
    edits=[{"old_string": "# A note on the module.", "new_string": "# A changed note on the module."}],
    cwd=_tc_base_repo, **TC_BUILDER)
add("builder-refuse: an Edit with a comment edit and a code content is denied by the Edit tool", "deny",
    rule=TC_RULE, tool="Edit", file_path=TC_PY, content="assert 2", old_string="# A note on the module.",
    new_string="# A changed note on the module.", cwd=_tc_base_repo, **TC_BUILDER)
