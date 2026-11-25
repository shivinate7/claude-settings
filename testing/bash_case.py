"""Reads the `case` statements of a bash script: each arm, and the alternatives of its pattern list.

The one home of the case reader that the layout checks (lint/test_list_layout.py) and the pinned scope verdicts
(lint/test_ci_scope.py) use. It is a tokenizer, not a bash parser. It knows single and double quotes, backslash
escapes and line continuations, `$(...)`, `$((...))`, `<(...)`, `${...}` and backticks as one word each, and a `#`
that opens a word as a comment. A `|` separates alternatives only outside those. A `;;`, `;&` or `;;&` ends an arm
body, and `esac` ends a case.

case_arms(src) -> [{"line": int, "case": int, "subject": str, "outer": tuple, "alts": [(text, line), ...]}, ...]
    One entry per arm, every nested case included, in source order. `case` is the line of the `case` word, which
    the arms of one case share. `subject` is that case word's subject, as written.
    `alts` holds each alternative's text, with line continuations removed, and the line its word starts on. `outer`
    holds the alternatives of each arm that encloses this one, outermost first, as a tuple of tuples.
"""

OPS = (";;&", ";;", ";&", "&&", "||", ";", "&", "|", "(", ")", "<", ">")


class ReadError(ValueError):
    """The text is not a script this reader can read: a quote, a `$(` or a `case` is never closed or opened."""


def _quoted_span(src, i, line):
    """src[i] is an opening `"`. -> (index past the closing quote, newlines in the span)."""
    k, nl, n = i + 1, 0, len(src)
    while k < n:
        c = src[k]
        if c == "\\":
            nl += src[k + 1:k + 2] == "\n"
            k += 2
            continue
        if c == '"':
            return k + 1, nl
        if c == "\n":
            nl += 1
        if c == "$" and src[k + 1:k + 2] == "(":
            k, more = _paren_span(src, k + 1, line)
            nl += more
            continue
        if c == "$" and src[k + 1:k + 2] == "{":
            k, more = _brace_span(src, k + 1, line)
            nl += more
            continue
        if c == "`":
            k, more = _backtick_span(src, k, line)
            nl += more
            continue
        k += 1
    raise ReadError("line %d: a double quote is never closed" % line)


def _paren_span(src, i, line):
    """src[i] is the `(` of `$(` or `<(`. -> (index past the matching `)`, newlines in the span)."""
    depth, k, nl, n = 0, i, 0, len(src)
    while k < n:
        c = src[k]
        if c == "\\":
            nl += src[k + 1:k + 2] == "\n"
            k += 2
            continue
        if c == "'":
            end = src.find("'", k + 1)
            if end < 0:
                raise ReadError("line %d: a single quote is never closed" % line)
            nl += src.count("\n", k, end)
            k = end + 1
            continue
        if c == '"':
            k, more = _quoted_span(src, k, line)
            nl += more
            continue
        if c == "#" and (k == 0 or src[k - 1] in " \t\n;(|&"):
            end = src.find("\n", k)
            k = n if end < 0 else end
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return k + 1, nl
        elif c == "\n":
            nl += 1
        k += 1
    raise ReadError("line %d: a `(` is never closed" % line)


def _brace_span(src, i, line):
    """src[i] is the `{` of `${`. -> (index past the matching `}`, newlines in the span)."""
    depth, k, nl, n = 0, i, 0, len(src)
    while k < n:
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k + 1, nl
        elif c == "\n":
            nl += 1
        k += 1
    raise ReadError("line %d: a `${` is never closed" % line)


def _backtick_span(src, i, line):
    end = src.find("`", i + 1)
    if end < 0:
        raise ReadError("line %d: a backtick is never closed" % line)
    return end + 1, src.count("\n", i, end)


def tokenize(src):
    """-> [(kind, text, line)] with kind "word", "op" or "nl". A word's text keeps its quotes and escapes."""
    toks, word, wline = [], [], [1]
    i, n, line = 0, len(src), 1

    def flush():
        if word:
            toks.append(("word", "".join(word), wline[0]))
            del word[:]

    while i < n:
        c = src[i]
        if c in " \t":
            flush()
            i += 1
            continue
        if c == "\n":
            flush()
            toks.append(("nl", "\n", line))
            line += 1
            i += 1
            continue
        if c == "\\" and src[i + 1:i + 2] == "\n":
            line += 1
            i += 2
            continue
        if c == "#" and not word:
            end = src.find("\n", i)
            i = n if end < 0 else end
            continue
        if not word:
            wline[0] = line
        if c == '"':
            end, more = _quoted_span(src, i, line)
            word.append(src[i:end])
            line += more
            i = end
            continue
        if c == "'":
            end = src.find("'", i + 1)
            if end < 0:
                raise ReadError("line %d: a single quote is never closed" % line)
            word.append(src[i:end + 1])
            line += src.count("\n", i, end)
            i = end + 1
            continue
        if c == "\\":
            word.append(src[i:i + 2])
            i += 2
            continue
        if c == "$" and src[i + 1:i + 2] == "(":
            end, more = _paren_span(src, i + 1, line)
            word.append(src[i:end])
            line += more
            i = end
            continue
        if c == "$" and src[i + 1:i + 2] == "{":
            end, more = _brace_span(src, i + 1, line)
            word.append(src[i:end])
            line += more
            i = end
            continue
        if c in "<>" and src[i + 1:i + 2] == "(":
            end, more = _paren_span(src, i + 1, line)
            word.append(src[i:end])
            line += more
            i = end
            continue
        if c == "`":
            end, more = _backtick_span(src, i, line)
            word.append(src[i:end])
            line += more
            i = end
            continue
        op = next((o for o in OPS if src.startswith(o, i)), None)
        if op:
            flush()
            toks.append(("op", op, line))
            i += len(op)
            continue
        word.append(c)
        i += 1
    flush()
    return toks


def _is_word(tok, text=None):
    return tok[0] == "word" and (text is None or tok[1] == text)


def _is_op(tok, text):
    return tok[0] == "op" and tok[1] == text


def _is_case_start(toks, i):
    return (i + 2 < len(toks) and _is_word(toks[i], "case") and toks[i + 1][0] == "word"
            and _is_word(toks[i + 2], "in"))


def _case(toks, i, arms, outer):
    """toks[i] is `case`. Records its arms and nested cases; -> the index past its `esac`."""
    n = len(toks)
    j = i + 3
    while j < n:
        if _is_word(toks[j], "esac"):
            return j + 1
        if toks[j][0] == "nl" or _is_op(toks[j], ";"):
            j += 1
            continue
        if _is_op(toks[j], "("):
            j += 1
        alts = []
        while True:
            if j >= n or toks[j][0] != "word":
                raise ReadError("line %d: a case pattern is not a word" % (toks[j][2] if j < n else -1))
            alts.append((toks[j][1], toks[j][2]))
            j += 1
            if j < n and _is_op(toks[j], "|"):
                j += 1
                continue
            break
        if j >= n or not _is_op(toks[j], ")"):
            raise ReadError("line %d: a case pattern has no `)`" % alts[0][1])
        j += 1
        arms.append({"line": alts[0][1], "case": toks[i][2], "subject": toks[i + 1][1], "outer": outer,
                     "alts": alts})
        inner = outer + (tuple(text for text, _ in alts),)
        while j < n:
            tok = toks[j]
            if tok[0] == "op" and tok[1] in (";;", ";&", ";;&"):
                j += 1
                break
            if _is_word(tok, "esac"):
                return j + 1
            if _is_case_start(toks, j):
                j = _case(toks, j, arms, inner)
                continue
            j += 1
        else:
            raise ReadError("line %d: a case arm has no `;;` and no `esac`" % alts[0][1])
    raise ReadError("line %d: a case has no `esac`" % toks[i][2])


def case_arms(src):
    toks = tokenize(src)
    arms, j, n = [], 0, len(toks)
    while j < n:
        if _is_case_start(toks, j):
            j = _case(toks, j, arms, ())
        else:
            j += 1
    return arms
