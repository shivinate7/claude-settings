"""The guard's mask-script family: the Workflow script lexer that masks strings and comments.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import re



SCRIPT_STRING = {q: re.compile(r"((?:\\.|[^\\%s])*)%s" % (q, q), re.DOTALL) for q in "'\""}
SCRIPT_TEMPLATE_TEXT = re.compile(r"((?:\\.|[^\\`$]|\$(?!\{))*)", re.DOTALL)
SCRIPT_REGEX = re.compile(r"/(?:\\[^\n]|\[(?:\\[^\n]|[^\]\\\n])*\]|[^/\\\[\n])+/")
SCRIPT_REGEX_AFTER = frozenset(",=:[!&|?{;(+-*%<>^~")


# Known limit: a regex literal is blanked, not lexed as code, and only when the previous non-space
# character is an operator, one of ( , = { ; : [ ! & | ? + - * % < > ^ ~, or the script starts. A
# postfix ++ or -- reads as division. A quote inside a regex literal after any other character (for
# example after a `)`), or a regex right after `return` or `typeof`, can hide an agent() call.
def mask_script(script: str):
    """Drop comments and replace each string literal with a \\x00N\\x00 token. Return (text, strings).
    One pass, linear. A backslash escapes the next character, so an escaped quote never closes a
    string. An unclosed opener stays as code. Once a scan for a closer fails, no later one can
    succeed, so a failed closer is remembered. A template becomes one token that holds its raw
    source, filled in at the closing backtick; a template with a `${` holds a (start, end, static)
    tuple instead: the span of the script, which the reader slices, and the raw template text with
    each `${...}` replaced by one \\x00, so no text line runs across an interpolation. The code in each `${...}` stays visible after the
    token, in parentheses. A `{` or `}` in that code moves a depth counter, and the `}` at depth 0
    resumes the template text. A template never closed by the end of the script is undone and its
    backtick stays as code."""
    out, strings, dead = [], [], set()
    stack = []  # brace depth inside each open `${`
    tstack = []  # [strings index, source start, has `${`, static text pieces] of each open template
    regex_dead = 0  # a regex scan that failed ran to this index: no `/` before it opens one
    mark = None  # (out length, strings length, index) where the outermost open template began
    i, n = 0, len(script)

    def regex_ok(j):
        """True when the previous non-space character allows a regex literal, or none exists."""
        j -= 1
        while j >= 0 and script[j].isspace():
            j -= 1
        if j >= 1 and script[j] in "+-" and script[j - 1] == script[j]:
            return False  # postfix ++ or --: a division follows
        return j < 0 or script[j] in SCRIPT_REGEX_AFTER

    def text(j):
        """Mask template text from j. Return the index after the closing backtick, or after the
        `${` that opens code, or -1 when the script ends first."""
        nonlocal mark
        k = SCRIPT_TEMPLATE_TEXT.match(script, j).end()
        tstack[-1][3].append(script[j:k])
        if script.startswith("${", k):
            stack.append(0)
            tstack[-1][2] = True
            out.append("(")
            return k + 2
        if script.startswith("`", k):
            idx, start, spans, pieces = tstack.pop()
            strings[idx] = (start, k, "\x00".join(pieces)) if spans else script[start:k]
            if not tstack:
                mark = None
            return k + 1
        return -1

    while True:
        if i < 0 or (i >= n and tstack):  # a template never closed: undo it, keep its backtick
            del out[mark[0]:], strings[mark[1]:]
            out.append("`")
            i, mark = mark[2] + 1, None
            stack.clear()
            tstack.clear()
            dead.add("`")
        if i >= n:
            break
        ch = script[i]
        if ch == "/" and script.startswith("//", i):
            j = script.find("\n", i)
            i = n if j < 0 else j
            out.append(" ")
        elif ch == "/" and script.startswith("/*", i) and "*/" not in dead:
            j = script.find("*/", i + 2)
            if j < 0:
                dead.add("*/")
                out.append(ch)
                i += 1
            else:
                out.append(" ")
                i = j + 2
        elif ch == "/" and i >= regex_dead and not script.startswith("/*", i) and regex_ok(i):
            m = SCRIPT_REGEX.match(script, i)
            if m is None:
                j = script.find("\n", i)
                regex_dead = n if j < 0 else j
                out.append(ch)
                i += 1
            else:
                out.append(" ")
                i = m.end()
        elif ch in SCRIPT_STRING and ch not in dead:
            m = SCRIPT_STRING[ch].match(script, i + 1)
            if m is None:
                dead.add(ch)
                out.append(ch)
                i += 1
            else:
                strings.append(m.group(1))
                out.append("\x00%d\x00" % (len(strings) - 1))
                i = m.end()
        elif ch == "`" and "`" not in dead:
            if not tstack:
                mark = (len(out), len(strings), i)
            tstack.append([len(strings), i + 1, False, []])
            strings.append(None)
            out.append("\x00%d\x00" % (len(strings) - 1))
            i = text(i + 1)
        elif stack and ch == "{":
            stack[-1] += 1
            out.append(ch)
            i += 1
        elif stack and ch == "}":
            if stack[-1]:
                stack[-1] -= 1
                out.append(ch)
                i += 1
            else:
                stack.pop()
                out.append(")")
                i = text(i + 1)
        else:
            out.append(ch)
            i += 1
    return "".join(out), strings

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
