"""The guard's rm-var family: a recursive delete on an unguarded variable.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import functools
import itertools
import os
import re
import sys

from guard_core import (
    PLAYWRIGHT_PS_SHELLS, _pwsh_script, basename, inline_script, resolve_command, segment_tokens,
    split_segments,
)


# THE UNGUARDED VARIABLE DELETE. Decision rm-on-a-variable-needs-a-guard: a recursive `rm` whose
# target has an unguarded expansion followed by `/` is refused, and the refusal prints the targets
# with every expansion written `${NAME:?}`. Segments, the command word and the `sh -c` script
# come from the shell walk above. `_RAW_WORD` only keeps the quote marks that
# `segment_tokens` drops, and `rm_call` checks that both reads agree on the word count.
# Limits: the debt notes (rm-var-unseen-forms).
_RAW_WORD = re.compile(r"""(?:\\.|'[^']*'|"(?:[^"\\]|\\.)*"|[^\s'"\\])+""")
_RM_PART = re.compile(r"""'[^']*'|"(?:[^"\\]|\\.)*"|[^'"]+|.""")
_RM_EXPANSION = re.compile(r"\$(?:\{(\w+)\}|(\w+))")
_RM_LITERAL = "literal path needed: "
# A variable is tainted when its assigned value or for-loop list starts with `~`, or when the command
# holds a source (`pwd` as a command word, $HOME, ${HOME, $PWD, ${PWD) anywhere: then every name it
# assigns or loops is tainted. No `$(…)` span parsing.
_RM_TAINT = re.compile(r"(?<![\w$-])(\w+)=(~)?|\bfor\s+(\w+)\s+in\s+(~)?")
_RM_SOURCE = re.compile(r"(?:^|[\s(`;&|/])pwd(?=$|[\s)`;&|])|\$(?:HOME|PWD)(?!\w)|\$\{(?:HOME|PWD)")


def rm_call(segment: str):
    """Return (tokens, at, flag words, target words, recursive) for an `rm` segment, else None.
    Words are raw (quotes kept). None also when the raw and shlex reads disagree on word count."""
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    at = resolve_command(tokens)
    raw = _RAW_WORD.findall(segment)
    if at is None or basename(tokens[at]) != "rm" or len(raw) != len(tokens):
        return None
    flags, targets, recursive, ended = [], [], False, False
    for token, word in zip(tokens[at + 1:], raw[at + 1:]):
        if not ended and token.startswith("-") and len(token) > 1:
            flags.append(word)
            ended = token == "--"
            recursive = recursive or token == "--recursive" or (
                not token.startswith("--") and bool(re.search("[rR]", token)))
        else:
            targets.append(word)
    return tokens, at, flags, targets, recursive


def _rm_taint_names(text: str) -> set:
    """Return the names whose value may be a home or cwd path."""
    names = {"HOME", "PWD"}
    source = bool(_RM_SOURCE.search(text))
    for m in _RM_TAINT.finditer(text):
        if source or m.group(2) or m.group(4):
            names.add(m.group(1) or m.group(3))
    return names


# The allow-list for `${NAME:?}` advice (ruling item 1). Every binding of a name must be
# `NAME=<literal>`, `for NAME in <literal words>` or `NAME=$(mktemp …)`. Built once per command.
_RM_EXPANSION_ANY = re.compile(r"\$(?:\{(\w+)(?::\?)?\}|(\w+))")
_RM_NAMES = re.compile(r"\$\{?(\w+)")
_RM_TRIGGER = re.compile(r"""\$(?:\{(\w+)(:\?)?\}|(\w+))"?/(?=[*?\[${}/"']|\.\.|$)""")
_RM_VALUE = re.compile(r"""(?:\\.|'[^']*'|"(?:[^"\\]|\\.)*"|[^\s'"\\;&|()<>])+""")
_RM_BIND = re.compile(r"(?<![\w$-])(\w+)(\+|\[[^\]]*\])?=")
_RM_MKTEMP = re.compile(r"""("?)\$\(\s*mktemp\b[^()$`;&|\n]*\)\1""")
_RM_FOR = re.compile(r"\bfor\s+(\w+)\s+in\s+([^;\n]*)")
_RM_OTHER_BIND = re.compile(r"\b(?:read|mapfile|readarray|getopts|select|printf\s+-v)\b[^;&|\n]*")
_RM_CD = re.compile(r"(?<![\w.-])(?:cd|pushd|popd)(?![\w-])")
_RM_MKTEMP_PATH = "/tmp/mktemp.X"


def _rm_literal(word: str):
    if len(word) > 1 and word[0] == word[-1] and word[0] in "'\"":
        word = word[1:-1]
    if not word or word[0] == "." or re.search(r"""\.\.|[~$`*?\[{}\\'"\s]""", word):
        return None
    return word


_RM_END = ("", ";", "&", "|", "\n", ")", "#", " ", "\t")
_RM_BLANK = re.compile(r"[ \t]*")


def _rm_prefixed(scope: str, i: int) -> bool:
    """True when the assignment ending at i is a prefix assignment, such as `X=/tmp rm …`."""
    while True:
        i = _RM_BLANK.match(scope, i).end()
        if scope[i:i + 1] in ("", ";", "&", "|", "\n", ")", "#"):
            return False
        m = _RM_BIND.match(scope, i)
        if not m:
            return True
        v = _RM_VALUE.match(scope, m.end())
        i = v.end() if v else m.end()


def _rm_values(scope: str) -> dict:
    """Return {name: [literal values]} for names whose every binding is safe, None otherwise."""
    vals = {}
    def put(name, value):
        if name in vals and vals[name] is None:
            return
        if value is None:
            vals[name] = None
        else:
            vals.setdefault(name, []).append(value)
    for m in _RM_BIND.finditer(scope):
        mk = _RM_MKTEMP.match(scope, m.end())
        vm = None if mk else _RM_VALUE.match(scope, m.end())
        end = mk.end() if mk else (vm.end() if vm else m.end())
        if mk and scope[end:end + 1] not in _RM_END:   # a mktemp value has nothing after the `)`
            value = None
        else:
            value = _RM_MKTEMP_PATH if mk else _rm_literal(vm[0] if vm else "")
        put(m.group(1), None if m.group(2) or _rm_prefixed(scope, end) else value)
    for m in _RM_FOR.finditer(scope):
        for w in _RM_VALUE.findall(m.group(2)) or [""]:
            put(m.group(1), _rm_literal(w))
    for m in _RM_OTHER_BIND.finditer(scope):
        for w in re.findall(r"\w+", m.group(0)):
            vals[w] = None
    return vals


def _rm_last_bind(scope: str) -> dict:
    """Return {name: offset of its last binding of any kind}, in one pass over scope."""
    last = {}
    for m in _RM_BIND.finditer(scope):
        last[m.group(1)] = m.start()
    for m in _RM_FOR.finditer(scope):
        last[m.group(1)] = m.start()
    for m in _RM_OTHER_BIND.finditer(scope):
        for w in re.findall(r"\w+", m.group(0)):
            last[w] = m.start()
    return last


@functools.lru_cache(maxsize=16)
def _rm_real(path: str) -> str:
    """Return the real path, case-folded on macOS and Windows, where the file system folds case.
    On Windows it has forward slashes, so the compares below hold on both systems."""
    if os.name == "nt":   # Git Bash `/c/...` and `/c` name drive C:. Not `_expanded`: no ~ or $VAR here.
        path = re.sub(r"^/([A-Za-z])(?=/|$)", r"\1:/", path)
    real = os.path.realpath(path)
    if os.name == "nt":
        return real.replace("\\", "/").lower()
    return real.lower() if sys.platform == "darwin" else real


def _rm_target_bad(path: str, cwd: str) -> bool:
    """True when path, or a glob's parent, is /, home, the cwd or a parent of the cwd."""
    if re.search(r"[*?\[]", os.path.basename(path)):
        path = os.path.dirname(path)
    cwd, home = _rm_real(cwd or "/"), _rm_real(os.path.expanduser("~"))
    # An absolute path skips the join, so on Windows a Git Bash `/c/...` reaches _rm_real intact.
    q = _rm_real(path if path.startswith("/") else os.path.join(cwd, path))
    up = q.rstrip("/") + "/"
    root = q == "/" or q == os.path.dirname(q)   # on Windows "/" resolves to the drive root
    return root or q in (cwd, home) or cwd.startswith(up) or home.startswith(up)


def _rm_word_safe(word: str, vals: dict, cwd: str) -> bool:
    """True when every expansion in the word has only safe bindings and no value makes the
    target /, home or the cwd."""
    plain = word.replace('"', "")
    names = sorted({a or b for a, b in _RM_EXPANSION_ANY.findall(plain)})
    if any(vals.get(n) is None for n in names):
        return False
    combos = [vals[n] for n in names]
    size = 1
    for c in combos:
        size *= len(c)
    if size > 64:
        return False
    for pick in itertools.product(*combos):
        mapping = dict(zip(names, pick))
        path = _RM_EXPANSION_ANY.sub(lambda m: mapping[m.group(1) or m.group(2)], plain)
        if _rm_target_bad(path, cwd):
            return False
    return True


def _rm_var_rewrite(word: str, ctx):
    """_rm_var_rewrite_raw, except that any error while judging gives the literal-path reason."""
    try:
        return _rm_var_rewrite_raw(word, ctx)
    except Exception:
        return word, 2


def _rm_var_rewrite_raw(word: str, ctx):
    """Return (word with every expansion guarded, 0 when not in the trigger shape, 1 when the
    allow-list clears the names, 2 when only a literal path will do). Text inside single quotes is
    a literal and stays as it is. ctx is (taint names, allow-list values, cwd, cd seen)."""
    taint, vals, cwd, moved = ctx
    def guard(match):
        return "${%s:?}" % (match.group(1) or match.group(2))
    out, live = [], []
    for part in _RM_PART.findall(word):
        if part[0] == "'":
            out.append(part)
        elif part[0] == '"' and len(part) > 1 and part.endswith('"'):
            out.append('"' + _RM_EXPANSION.sub(guard, part[1:-1]) + '"')
            live.append(part)
        else:
            out.append(_RM_EXPANSION.sub(guard, part))
            live.append(part)
    live = "".join(live)
    kind = 0
    for m in _RM_TRIGGER.finditer(live):
        if m.group(2):
            kind = 2 if (m.group(1) in taint) else kind
        elif moved or not word.lstrip('"').startswith("$") or not _rm_word_safe(live, vals, cwd):
            kind = 2
        else:
            kind = max(kind, 1)
    return "".join(out), kind


def rm_var_hits(text: str, cwd: str = "", depth=0, outer: str = "", after: str = "") -> list:
    """Return the flagged `rm` calls of a command, each as `rm FLAGS TARGETS` with every
    expansion in a flagged target guarded `:?`, or _RM_LITERAL when only a literal path will do.
    `sh -c`, `eval` and `pwsh -Command` are walked, and outer bindings count inside them. `after`
    is the outer text that follows the wrapper: a binding there comes after every inner rm."""
    found = []
    scope = outer + "\n" + text
    ctx = (_rm_taint_names(scope), _rm_values(scope), cwd, bool(_RM_CD.search(scope)))
    cursor = 0
    last = _rm_last_bind(text + "\n" + after)   # offsets past len(text) lie in `after`
    for segment in split_segments(text):
        at_seg = text.find(segment, cursor)
        if at_seg >= 0:
            cursor = at_seg + len(segment)
        call = rm_call(segment)
        if call:
            _, _, flags, targets, recursive = call
            rewritten = [(w, hit) for w, hit in (_rm_var_rewrite(t, ctx) for t in targets) if hit]
            if recursive and any(hit == 1 for _, hit in rewritten):
                # every binding precedes the rm: a name bound later is unsafe, and so is a
                # segment whose place in the text is unknown
                rewritten = [(w, 2 if hit == 1 and (at_seg < 0 or any(
                    last.get(n, -1) >= cursor for n in _RM_NAMES.findall(w))) else hit)
                    for w, hit in rewritten]
            if rewritten and recursive:
                for kind in (2, 1):
                    words = [w for w, hit in rewritten if hit == kind]
                    if words:
                        found.append(_RM_LITERAL if kind == 2 else " ".join(["rm"] + flags + words))
            continue
        tokens = segment_tokens(segment)
        at = resolve_command(tokens) if tokens else None
        if at is None or depth > 3:
            continue
        word = basename(tokens[at]).lower()
        script = " ".join(tokens[at + 1:]).replace("\\$", "$") if word == "eval" else (
            _pwsh_script(tokens) if word in PLAYWRIGHT_PS_SHELLS else inline_script(tokens))
        if script:
            found += rm_var_hits(script, cwd, depth + 1, scope,
                                 text[cursor if at_seg >= 0 else 0:] + "\n" + after)
    return found


def rm_var_reason(hits) -> str:
    literal = _RM_LITERAL in hits
    hits = [h for h in hits if h != _RM_LITERAL]
    if literal:
        return (
            "a recursive delete under $HOME, $PWD, ~ or a variable set from them can remove the "
            "home or working folder, and a ${NAME:?} guard does not clear it. Retry with a "
            "literal path: name the one directory you mean." +
            (" The other targets need every expansion written ${NAME:?}, which stops the "
             "command when the variable is empty: " + "; ".join(hits) if hits else "")
        )
    return (
        "a recursive delete with an unguarded variable in its path can remove far more than "
        "intended when the variable is empty. Retry with every expansion written ${NAME:?}, "
        "which stops the command when the variable is empty. Retry with: " + "; ".join(hits)
    )

# A DELETE AFTER A CD. Decision rm-after-cd-names-an-absolute-path: a recursive `rm` with a relative
# target, after `cd X` joined by `;`, `&&` or a newline, is flagged. Claude Code's prompt cannot follow
# the cd, and a failed cd runs the rm in the working folder. Segments and tokens come from the same
# walk as above, so quotes and comments are not text to it. `sh -c` bodies are not walked.
_CD_OPENERS = ("(", "{", "!", "time")
_CD_JOINS = (";", "&&", "\n", "")


def _cd_word(segment: str):
    """Return the raw directory word of a `cd` segment, "" when it names none, None when not a cd."""
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    raw = _RAW_WORD.findall(segment)
    i = 0
    while i < len(tokens) and tokens[i] in _CD_OPENERS:
        i += 1
    if i < len(tokens) and tokens[i].startswith("(") and tokens[i][1:] == "cd":
        tokens[i] = "cd"
    if i >= len(tokens) or tokens[i] != "cd":
        return None
    dirs = [k for k in range(i + 1, len(tokens)) if not tokens[k].startswith("-") or tokens[k] == "-"]
    return raw[dirs[-1]] if dirs and len(raw) == len(tokens) else ""


def _cd_relative(word: str) -> bool:
    bare = word.lstrip("\"'")
    return bool(bare) and bare[0] not in "/$~"


def _cd_remedy(flags, target: str, cd_word: str) -> str:
    """Return `rm FLAGS <dir>/<target>`: a variable dir is written "${NAME:?}", a literal absolute
    dir as it is, and anything else "${DIR:?}", which stops the command until the person sets DIR
    to the full path."""
    base = cd_word.strip("\"'")
    named = re.fullmatch(r"\$(?:\{(\w+)\}|(\w+))", base)
    if named:
        base = '"${%s:?}"' % (named.group(1) or named.group(2))
    elif not base.startswith("/") or re.search(r"[\s$`*?\[{}~\\'\"]", base):
        base = '"${DIR:?}"'
    target = target[2:] if target.startswith("./") else target
    return " ".join(["rm"] + flags + [base + "/" + target])


def rm_after_cd_hits(text: str) -> list:
    """Return each flagged `rm` as `rm FLAGS <dir>/<target>`, in the absolute form."""
    ends = []
    found = []
    moved = None
    for segment, end in zip(split_segments(text, ends), ends):
        word = _cd_word(segment)
        if word is not None:
            moved = word if end in _CD_JOINS else None   # `cd X || rm …` is no landed cd
            continue
        call = rm_call(segment) if moved is not None else None
        if not call:
            continue
        _, _, flags, targets, recursive = call
        targets = [t[:-1] if t.endswith((")", "}")) and not t.endswith(("\\)", "\\}")) else t
                   for t in targets]
        targets = [t for t in targets if t and not re.match(r"\d*[<>&|]", t)]   # a redirect word is no target
        if recursive and any(_cd_relative(t) for t in targets):
            found += [_cd_remedy(flags, t, moved) for t in targets if _cd_relative(t)]
    return found


def rm_after_cd_reason(hits) -> str:
    return (
        "a recursive delete that follows a cd names its target relative to a folder the "
        "permission prompt cannot see, and when the cd fails the delete runs in the working "
        "folder. Retry with no cd: give the target as a full path, or as a quoted variable that "
        "holds one. Retry with: " + "; ".join(hits)
    )


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
