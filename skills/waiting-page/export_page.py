#!/usr/bin/env python3
"""Copy an artifact's page, its files and its database into the repo, build the database back, and merge a copy into a live page (skill waiting-page, decision waiting-data-in-repo).

The copy in git is a backup for recovery and account moves. The page's database is the one store (decision
waiting-page-one-store). The one exception is the filing check in hooks/feedback_guard.py (debt filing-check-reads-copy).

Four modes: export (--fetched, --out), rebuild (--rebuild, --batches), merge (--merge, --live, --batches) and --all.

Export, the writer's step at each wake and before each republish:

    python3 ~/.claude/skills/waiting-page/export_page.py --fetched DIR --out WAITING_DIR [--page FETCHED.html]
        [--allow-empty COLLECTION]

DIR holds `<collection>/<doc_id>.json` for each of the five collections, as `ArtifactData list ... out_dir=DIR`
saves them; an empty collection is an empty folder. A script cannot call that tool, so the session fetches first.
The session touches `.complete` in each collection folder after the last list page, so a fetch that stopped early
shows: a collection with no marker is unknown. A collection that is empty now while the copy holds docs of it is
unknown too, unless the session names it with --allow-empty.
WAITING_DIR is the `waiting-data` folder of the record branch (`layout.py path <root> waiting-data`). With --page,
the page's bytes land in `page/page.html`, and its designData block in `page/designData.json`. A file is written
only when its bytes differ. The script never runs git: the session commits.

Verdict, one line, then exit:
  changed N  N files written or deleted in WAITING_DIR; exit 0
  same       nothing differs; exit 0
  refused    a value or key has the shape of a secret or of personal data; one line per find (file, JSON path,
             kind, never the value); nothing is written; exit 1
  unknown    a collection folder or its marker is missing, a file is not one JSON doc, a collection emptied, or the
             page has no or two designData blocks; nothing is written; exit 2
  unknown    the run crashed (one line, nothing written); exit 3
Picture check, with --page: after the copy is written, each fetched item that carries a picture and that the page draws as an
open decision (not closed, not a ruling, not answered) is run through check_designs.mjs, the page's own `pictureProblem` in
Chromium (page_check.py is the one home). A miss prints `held item <n>: <the page's sentence>` after the verdict line, one
per item, and the run exits 4: fix the item, export again, and do not republish while one is held. A check that cannot run
(no node, no Playwright or Chromium), or an open pictured item with no page file, prints one `checks unknown: <why>` line
before the verdict; the copy is written and the exit code is as without checks. The checker gets the fetched answers
(`--answers`) and skips an item the page's own `isAnswered` draws as answered. One time budget (page_check.CHECK_BUDGET)
spans the items of a run: items left unchecked when it runs out print `checks unknown: time budget spent, <k> item(s) not
checked`, with the exit code as without checks. Under --all, a waiting-page entry whose own `collections` lacks `items` or
`answers` runs no check: it prints `<id>: checks unknown: collections lack <name>`, its copy is written, and the exit is 2.
Every doc is scanned, as parsed JSON, before the first write: each string value, each key, each doc id and each
10 or 11 digit number (a phone). The page text and each supporting text file are scanned as text with the same
shapes, except that a version pin such as `react@18.3.1` and a retina name such as `logo@2x.png` are not emails.
Credentials in a URL, `scheme://user:password@host`, refuse on any host, an IP host too. A file that is not UTF-8 is
read as latin-1; only a file with a NUL byte is binary and not scanned, whatever its name. Only the shape counts:
words such as "token budget" or "password manager" pass. So do a password word with a placeholder, a mask or a plain
word as its value and only blanks or plain prose after it on its line (a function word, then letter words, with no
non-function word later in the line after a `,` `;` or and/or/but/is/are; the `,` `;` or `.` that ends the value does
not count),
`PWD=<path>`, a no-reply address and an ssh remote of a public git host.
A personal fact in plain words passes too. A postal address (street, PO box, "City, ST ZIP") is a shape.
A doc is written with sorted keys, two-space indent and a final newline, so an unchanged doc is byte-identical. A doc no
longer fetched is deleted from its collection folder; a truncated fetch deletes docs, and git history keeps them.

Check, before a republish, writes nothing:

    python3 ~/.claude/skills/waiting-page/export_page.py --check --fetched DIR --page FILE

The same item checks. A miss prints its `held item` line, exit 4. Else `checks pass`, exit 0. Unknown: `checks unknown: <why>`,
exit 3, which includes `checks unknown: time budget spent, <k> item(s) not checked`; a held item (4) wins over it. The writer
holds the republish on any exit but 0: a check that cannot read its input fails, never passes.

Rebuild, the recovery path. It reads only the repo copy, never the live page:

    python3 ~/.claude/skills/waiting-page/export_page.py --rebuild WAITING_DIR --batches OUT_DIR [--collections NAME ...]

Writes OUT_DIR/batch-NNN.json, each a JSON list of at most 50 `{op: "set", collection, doc_id, data}` entries and
under 900,000 bytes, one entry per doc in WAITING_DIR except `page/`, and prints `batches K docs N`. The session
sends each list as an `ArtifactData batch`. Unknown, exit 2: a missing or empty WAITING_DIR, a folder in it that is
neither one of the five collections (or the `--collections` names) nor `page/`, or one doc over the byte cap.
For an artifact other than the waiting page, `--collections NAME [NAME ...]` names its collections (the registry
entry's `collections`). They replace the five as the allowed folders, and a batch entry's `collection` is the folder
name. A named collection with no folder is empty and fine; a folder not named is unknown, even one of the five.
`--collections` without `--rebuild`, a name that is not a collection slug, or the name `page` is a usage error, exit 2.

Every artifact, the step "Before you switch Claude accounts":

    python3 ~/.claude/skills/waiting-page/export_page.py --all REPO_ROOT --fetched DIR --worktree RECORD_WORKTREE
        [--allow-empty COLLECTION] [--account LABEL]

REPO_ROOT holds the extras file with the artifacts registry (lint/layout.py `artifacts()`). DIR holds one folder per
artifact id, each laid out as in a single export, plus `page.html` and `files/<path>` (the page's supporting files).
Each entry exports the collections it lists to its export path under RECORD_WORKTREE (the waiting page: the
waiting-data folder; any other artifact: `artifacts/<id>/`), with the same scan and mirror as one export. Any role's
`<id>/page.html` lands at `page/page.html` there, and `<id>/files/<path>` at `page/files/<path>`; a waiting-page entry
also exports its designData block. A supporting file no longer fetched stays in the copy; history is the delete.
An entry with `"export": false` prints `<id>: skipped - no export`, needs no folder in DIR, writes nothing and
counts as exit 0. An entry with `"collections": []` is page-only: its page and files export, and no database does.
With --account LABEL, an entry whose account differs prints `<id>: skipped - account <its account>` and is treated the
same way, so a session that can read only one account's pages exports those and holds the rest. A LABEL that is empty or
that no entry's account holds prints one line, `unknown - --account ... matches no registry entry's account ...`, writes
nothing and exits 2. Without the flag every entry exports. A page-only entry whose fetched folder has no `page.html`
prints `<id>: unknown - ...` that names `page.html`, writes nothing and counts as exit 2. Each other artifact prints one line `<id>: <verdict>`, and a find's lines start with `<id>:` too. One artifact's refusal or
unknown leaves its own folder as it was and holds back no other. Exit: 0 when every artifact is changed or same; else
the worst of 1 (refused), 2 (unknown: also a registry that is missing, empty or unreadable) and 3 (a crash); 4 (a held
item) only when none of those happened. The waiting-page entry prints each `held item` line after its verdict, prefixed `<id>: `.

Merge, a second account's copy into a live page. It reads the repo copy and a fetch of the live page:

    python3 ~/.claude/skills/waiting-page/export_page.py --merge COPY_DIR --live LIVE_DIR --batches OUT_DIR [--collections NAME ...] [--live-page FETCHED.html]

COPY_DIR holds the --rebuild layout. LIVE_DIR holds the fetched layout, one folder per collection with its `.complete`
marker. OUT_DIR gets batch-NNN.json files as --rebuild writes them (the same split and caps), with one `set` entry for
each (collection, doc_id) of the copy that the live page lacks. The live page wins: a doc it holds is never written.
A copied item whose `n` is taken, by a live item or an earlier written copied item (sorted doc_id order), takes the next
free `n` above the highest in either folder, and its answer takes the same `n`. A copy answer is not written when the
live page holds its item (it counts in kept-live). OUT_DIR/renumbered.json maps each old `n` to its new `n`, string keys,
written even when empty. When the copy holds page/designData.json, --live-page (the live page's html) is required, and
OUT_DIR/designData.json holds the live page's designData plus each copy key it lacks. The last line is
`batches K docs N kept-live S renumbered R designs D`. Unknown, exit 2: a missing or empty copy, a missing live folder,
a live collection with no marker, a folder that is no collection in either, a doc over the cap, copy designs with no
--live-page or a live page with no designData block, or nothing left to write.
`--merge` without `--live` or `--batches` is a usage error, exit 2. `--collections` works as with --rebuild.

Cost: one python process, one read of each file, writes only for a changed doc. No git, no network, no timer.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import splice  # noqa: E402  the one home of the designData block's span
import page_check  # noqa: E402  the one home that runs the page's picture check

# The same five as lint/layout.py WAITING_COLLECTIONS. A copy, because a single export and the rebuild must run with no
# lint/ beside them: the recovery path may not depend on the repo it recovers (verification-recovery-independent-of-state).
COLLECTIONS = ("items", "answers", "groups", "asks", "meta")
COLLECTION_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")  # copy of lint/layout.py COLLECTION, for the same reason
PAGE_FOLDER, DESIGN_FILE, PAGE_FILE, FILES_FOLDER = "page", "designData.json", "page.html", "files"
MARKER = ".complete"  # the session touches it in a collection folder after the last list page
BATCH_SIZE = 50
BATCH_BYTES = 900000  # one ArtifactData batch call stays under about 1 MB
REFUSED, UNKNOWN, CRASH, HELD = 1, 2, 3, 4
CHECK_COLLECTIONS = ("items", "answers")  # what the picture check reads

STREET_WORDS = ("Street", "St", "Avenue", "Ave", "Road", "Rd", "Drive", "Dr", "Lane", "Ln", "Boulevard", "Blvd", "Way",
                "Court", "Ct", "Place", "Pl", "Circle", "Cir", "Terrace", "Ter", "Parkway", "Pkwy", "Park", "Trail", "Trl",
                "Highway", "Hwy")
STATE_CODES = ("AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND"
               "|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY")
# The user part of a URL credential holds no quote, bracket, paren or `|`, so minified code cannot start a match. Two
# template forms are the exceptions, since a templated user is still a user: a braced field with no quote or blank in it
# (`{user}`, `${USER}`, `{{user}}`, `{cfg.user}`, `{user!r}`, `{cfg[user]}`, `${var.db_user}`) and a percent field
# (`%(user)s`).
URL_USER = r"(?:[^/?#\s@:\"'`()\[\]{}|]|\{+[^{}\"'`\s/?#@]*\}+|%\(\w+\)[sd])+"
# A password that starts with anything but a quote or backtick is a literal, even with a `+`, `|`, bracket, paren or a
# later quote in it (`O'Neil2020`). The `@` after it is a credential, whatever follows, a quoted or templated host
# included (`"postgres://u:pw@" + host`, `u:pw@{db_host}`).
URL_PLAIN_PASSWORD = r"[^/?#\s@\"'`][^/?#\s@]*"
# A password that starts with a quote or backtick is the join of two string literals (`"http://h:"+port+"@"`), so it is
# a credential only when a host starts after its `@`.
URL_QUOTED_PASSWORD = r"[\"'`][^/?#\s@]*"
# What may follow the `@` of a quote-led password: a bracketed IPv6 host (`[::1]`), or anything but a quote, bracket or
# `|`, which is code.
URL_HOST_START = r"(?:(?=\[[0-9A-Fa-f.]*:)|(?![\"'`()\[\]{}|]))"
# Everyday words that end in `key`. A lookbehind on the letters before `key` in each (`mon`, `whis`) makes a `key`
# right after them no key word, so `monkey: Banana12345` passes. The stem must start the word (string start or a
# non-letter before it): `commonKey` and `returnKey` hold the stems `mon` and `turn` but are credential names. Any
# other `key`, `secret`, `token` or `cookie` in a name counts, however it is glued to the word before it.
EVERYDAY_KEY_WORDS = ("monkey", "hotkey", "turkey", "turnkey", "donkey", "whiskey", "jockey", "hockey", "lackey")
KEY_WORD = r"(?:secret|token|cookie|" + "".join("(?<!(?<![A-Za-z])%s)" % w[:-3] for w in EVERYDAY_KEY_WORDS) + r"key)"
# A credential name: a key word, then name characters up to the next key word, then `=` or `:`. Each name character is
# read once, so a long name or a long run scans in linear time.
CREDENTIAL_NAME = KEY_WORD + r"(?:(?!" + KEY_WORD + r")[A-Za-z0-9_-])*[\"']?[ \t]*(?P<sep>[=:])[ \t]*[\"']?"
VALUE_CHARS = r"[A-Za-z0-9+/_.~%=-]"  # the characters of a credential value
# The `credential-name` shape looks for the letter and the digit of a value in its first VALUE_LOOKAHEAD_MAX + 1
# characters: a lookahead to the end of a long run, from each key word in it (`key=key=...`), makes the scan quadratic.
# A longer value is matched whole by LONG_CREDENTIAL_VALUE and read once by long_value_is_no_secret.
VALUE_LOOKAHEAD_MAX = 256
# It has no lookahead and no end condition: a value shorter than its bound fails within that many characters, and a
# match takes the whole run, so finditer reads each run once. A key word inside the run starts no match of its own,
# so its value is read only as part of this one: after `key=` + 260 letters, `token: ` + 300 digits + `a` passes,
# because the run ends at the `:` and `token` lies inside the match, so the digits and the `a` are never its value.
LONG_CREDENTIAL_VALUE = re.compile(
    CREDENTIAL_NAME + r"(?P<value>" + VALUE_CHARS + r"{" + str(VALUE_LOOKAHEAD_MAX + 1) + r",})", re.I)
# Each shape is a token or a value that names a person or opens an account. The lookbehinds keep a match
# from starting inside a longer word ("risk-" and "btn-sk-" are not "sk-").
SECRET_SHAPES = (
    ("github-token", re.compile(r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("api-key", re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")),
    ("stripe-key", re.compile(r"(?<![A-Za-z0-9_-])[sr]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("docker-token", re.compile(r"(?<![A-Za-z0-9_-])dckr_pat_[A-Za-z0-9_-]{20,}")),
    # `(?<!\d)`, not `\b`: a bot URL, `api.telegram.org/bot<token>`, has a letter before the id.
    ("telegram-bot-token", re.compile(r"(?<!\d)\d{8,10}:[A-Za-z0-9_-]{35}(?![\w-])")),
    ("google-key", re.compile(r"(?<![A-Za-z0-9_-])AIzaSy[A-Za-z0-9_-]{33}")),
    ("gitlab-token", re.compile(r"(?<![A-Za-z0-9_-])glpat-[A-Za-z0-9_-]{20,}")),
    ("aws-key-id", re.compile(r"(?<![A-Z0-9])A[KS]IA[A-Z0-9]{16}(?![A-Z0-9])")),
    ("slack-token", re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]+")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")),
    ("auth-header", re.compile(r"\bAuthorization:\s*(?:Bearer|Basic)\s+\S+", re.I)),
    ("cookie-header", re.compile(r"\bCookie:\s*[^\s=;]+=\S+", re.I)),
    ("session-cookie", re.compile(r"(?<![A-Za-z0-9_.])connect\.sid=\S+")),
    ("url-secret", re.compile(r"[?&](?:access_token|key|sig|token)=[^&\s#]+", re.I)),
    # `scheme://user:password@host`, on any host: a version pin after the `@` is blanked, so an IP host is caught here.
    # The user part holds no quote, bracket or `|`, except inside a template field: minified code runs
    # `"https://a"})];x||y:z@` together. The password may hold them. A quote-led password is code when a quote, bracket
    # or `|` follows the `@`, unless an IPv6 host opens there: `"http://h:"+port+"@"`. Any other password is a literal
    # and always refuses.
    ("url-credentials", re.compile(
        r"://" + URL_USER + r":(?:" + URL_PLAIN_PASSWORD + r"@|" + URL_QUOTED_PASSWORD + r"@" + URL_HOST_START + r")")),
    # The value is captured in a lookahead, so a match ends at the separator and a later password word on the same line
    # (`password:!0};pwd=hunter2`) is a match of its own. found.end(2) is the end of the value.
    # The lookbehind takes `_` too, so a name starts at its run's first character and a long run is read once.
    ("password", re.compile(r"(?<![A-Za-z0-9_])([A-Za-z0-9_]*(?:password|passwd|pwd))[ \t]*[=:][ \t]*(?=(\S+))", re.I)),
    # The lookbehind starts the local part at its run's first character only: a start at each character re-reads a long run.
    ("email", re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")),
    # Bare "Bearer <token>" or "Basic <credential>" with no header name: 20 or more token characters, so prose such as
    # "Bearer tokens" or "Basic idea" passes.
    ("bearer", re.compile(r"(?<![A-Za-z0-9])(?:Bearer|Basic)[ \t]+[A-Za-z0-9._~+/=-]{20,}")),
    # A name that holds secret, token, key or cookie in any case form (API_SECRET, X-API-Key, apiKey, authtoken, NPMTOKEN,
    # SECRET_KEY_BASE, "clientSecret") set to a literal that looks random: 8 or more characters with a letter and a
    # digit. The key word may sit anywhere in the name; only the everyday words of EVERYDAY_KEY_WORDS are no key word.
    # A match starts at a key word and takes name characters up to the next key word, so each name character is read
    # once and a long name or a long run scans in linear time; the last key word of a name is the one that reaches the
    # `=` or `:`. A number, a "$VAR" or "${{ ... }}" reference and a plain word pass, and so does a label with a word
    # between, as in "token budget: 200000". A second branch takes a value with no digit: 12 or more of [A-Za-z_-] that
    # end the value (end of line, a closing quote, `,`, `;` or `}`) and have no camelCase hump (3 lower-case letters
    # then a capital; a hump after 1 or 2, as in `QwErTy`, is random), so `accessTokenValue`,
    # `localStorage.getItem(` and prose such as "Token: Authorization needed" pass. A letters-only value that reads as
    # words (letters_are_words) passes too, after a `:` only. A 2-3 letter prefix, an environment word and a digit part
    # (`sk-live-ab12`) is a key shape, so it is refused; plain hyphen words (`automations-v3-review`) are a name, so they pass.
    ("credential-name", re.compile(
        CREDENTIAL_NAME + r"(?:"
        r"(?=" + VALUE_CHARS + r"{0," + str(VALUE_LOOKAHEAD_MAX) + r"}[A-Za-z])"
        r"(?=" + VALUE_CHARS + r"{0," + str(VALUE_LOOKAHEAD_MAX) + r"}\d)"
        r"(?P<mixed>" + VALUE_CHARS + r"{8,})"
        r"|(?!(?-i:[A-Za-z_-]*[a-z]{3}[A-Z]))(?P<letters>[A-Za-z_-]{12,})(?=[\"']?[ \t]*(?:[,;}\r\n]|\Z)))", re.I)),
    # A credential value longer than the lookaheads above read: refused when it has a letter and a digit anywhere.
    ("credential-name", LONG_CREDENTIAL_VALUE),
    # A well-known cookie name set with "=" to a value of 8 or more characters with a digit in it.
    ("cookie-value", re.compile(
        r"(?<![A-Za-z0-9_.-])(?:cf_clearance|__cf_bm|sessionid|session_id|sid|csrftoken|PHPSESSID|JSESSIONID)[ \t]*=[ \t]*"
        r"(?=[A-Za-z0-9+/_.~%-]*\d)[A-Za-z0-9+/_.~%-]{8,}", re.I)),
    # A postal address. Street: a house number, one to three capitalised name words (or an ordinal such as 5th), then a
    # capitalised or all-caps street word, so "step 3 on the road map" and "a 2 way merge" pass. A dot ends a name word
    # only after an initial or Mt, St or Ft, and a number after a colon is a time, so "5 PM. Way forward" and
    # "13:44 CDT. Lane 2" pass. PO box: needs the box number.
    ("address", re.compile(
        r"(?<![A-Za-z0-9_.:-])\d{1,5}[ \t]+(?:(?:(?:[A-Z]|Mt|St|Ft)\.|[A-Z][A-Za-z]*|\d+(?:st|nd|rd|th))[ \t]+){1,3}"
        r"(?:" + "|".join(w + "|" + w.upper() for w in STREET_WORDS) + r")\b(?![\w-])")),
    ("address", re.compile(r"(?<![A-Za-z])P\.?[ \t]?O\.?[ \t]*Box[ \t]+\d+", re.I)),
    # City, a USPS state code and a ZIP or ZIP+4, after a comma: "Austin, TX 78701".
    ("address", re.compile(
        r"(?<![A-Za-z0-9])[A-Z][A-Za-z.]*(?:[ \t][A-Z][A-Za-z.]*)*,[ \t]*(?:" + STATE_CODES + r")[ \t]+\d{5}(?:-\d{4})?(?!\d)")),
)
# A value after a password word that names no secret: a word, a mask, a template placeholder or (after PWD) a path,
# after trailing `.,;`, a closing backtick, a `)` or `]` that closes a wrapper opened before the match, and one pair of
# wrapping quotes or brackets are taken off (bare_value). Only blanks or plain prose (rest_is_prose: a function word,
# then letter words, and after a `,` `;` or and/or/but/is/are only function words) may follow it on its line: another
# word there may be the secret (`none hunter2`). Anything else is refused.
PLAIN_VALUES = frozenset(("optional", "required", "none", "null", "empty", "unset", "hidden", "redacted", "omitted"))
JS_BOOLEANS = frozenset(("!0", "!1"))  # minified `true` and `false`
# `!0` or `!1` after a password word. It is code, no value, when what follows it is code-shaped (see boolean_run_is_code).
JS_BOOLEAN_START = re.compile(r"!(?:0|1)")
# The next member of a minified run: a `,` or `;`, then a name and its `:` or `=`.
JS_RUN_NEXT = re.compile(r"[,;]\s*[\"']?[A-Za-z_$][\w$]*[\"']?\s*[:=]\s*")
# A JS keyword then `-` and a number only: code after a `case "keyup":`, not a literal value.
JS_KEYWORD_VALUE = re.compile(r"(?:return|void|typeof|throw)(?:-\d+)?")
MASK_VALUE = re.compile(r"[*•#]{3,}|[xX]{3,}")
# `<placeholder words>` has no digits. A variable reference has an ALL_CAPS name, so `$Tr0ub4dor` and `${hunter2}` refuse.
PLACEHOLDER_VALUE = re.compile(
    r"<[A-Za-z_ -]+>|\$\{[A-Z][A-Z_]*\}|\{\{[A-Z][A-Z_]*\}\}|\$[A-Z][A-Z_]*|%[A-Z][A-Z_]*%")
REST_OF_LINE = re.compile(r"[^\r\n]*")  # the text after a password value, up to its line end
# Prose after a value: a function word first, then only letter words. A digit, a symbol or a word that is no function
# word right after the value (`none hunter2`, `none, hunter2`) is not prose, and a value must not hide a secret after a
# plain word. A `,` `;` or `.` that the value takes (`none,`) never reaches the separator test below, so
# `password: none, then swordfish` passes: the rest is a function word then letter words.
PROSE_FUNCTION_WORDS = ("a", "an", "the", "for", "to", "in", "on", "at", "of", "by", "with", "from", "as", "if", "when",
                        "while", "until", "unless", "and", "or", "but", "is", "are", "since", "because", "so", "then")
PROSE_REST = re.compile(
    r"[ \t]+(?:" + "|".join(PROSE_FUNCTION_WORDS) + r")"
    r"(?:[ \t,;]+[A-Za-z][A-Za-z'-]*)*[.,;:!?]*[ \t]*", re.I)
# After a `;`, a `,` or one of these words, a word that is no function word may be a second value (`default is
# swordfish`, `none and swordfish`), so the prose is refused. Only function words may follow such a separator.
PROSE_SEPARATORS = frozenset(("and", "or", "but", "is", "are"))
PROSE_TOKEN = re.compile(r"[A-Za-z][A-Za-z'-]*|[;,]")  # one pass over the line: bounded, no nested repeat
WRAP_PAIRS = frozenset(('""', "''", "[]", "()"))  # one pair around the value is no part of it
SHELL_PATH = re.compile(r"[~/][\w./~-]*")  # path characters only: no `;`, `&`, `=` or space can hide a second keyword
SHELL_PWD = "PWD"  # the shell's working-directory variable; with a path value it is no password
NO_REPLY_NAME = re.compile(r"(?:do[-_.]?not[-_.]?|no[-_.]?)reply", re.I)  # a mailbox that names no person
PUBLIC_GIT_HOSTS = frozenset(("github.com", "gitlab.com", "bitbucket.org"))  # `git@host:` is their ssh remote, no person
# A phone in a string has a country code and separated groups, or the "(xxx) xxx-xxxx" form, or groups of 3, 3 and 4
# digits joined by one separator. A bare run of digits is never one: a PO number or a timestamp is not a phone.
PHONE_COUNTRY = re.compile(r"(?<![\w+])\+\d{1,3}[\s.\-]*\(?\d{1,4}\)?(?:[\s.\-]+\d{2,4}){1,4}(?!\d)")
PHONE_OTHER = (
    re.compile(r"(?<!\d)\(\d{3}\)\s*\d{3}[\s.\-]\d{4}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}([-. ])\d{3}\1\d{4}(?!\d)"),
)
VERSION_PIN = re.compile(r"@\d+(?:\.\d+)*(?![\w.-]*[A-Za-z])")  # `@18.3.1` in a CDN address
# `logo@2x.png`: a retina image name, not an email. Only an image extension after the suffix makes it one.
RETINA_NAME = re.compile(r"@\d+x(?=\.(?:png|jpe?g|gif|webp|avif|svg|bmp|ico)\b)", re.I)
DATE_START = re.compile(r"\d{4}-\d{2}-\d{2}")
PHONE_DIGITS = (10, 11)  # a JSON number of this many digits is a phone; 13 digits is an epoch in milliseconds


class Stop(Exception):
    """The run ends with a verdict and a code, and has written nothing."""

    def __init__(self, verdict, code):
        super().__init__(verdict)
        self.code = code


def is_phone(text):
    """True when `text` holds a phone-shaped run. A country-code form with fewer than ten digits, or one that
    runs into an ISO date, is not a phone."""
    for found in PHONE_COUNTRY.finditer(text):
        whole = found.group(0)
        if sum(c.isdigit() for c in whole) >= 10 and not DATE_START.search(whole):
            return True
    return any(shape.search(text) for shape in PHONE_OTHER)


def bare_value(value):
    """`value` without trailing punctuation, a closing backtick, a `)` or `]` that closes a wrapper opened before the
    match, and one pair of wrapping quotes or brackets."""
    value = value.rstrip(".,;")
    if value[-1:] == "`":  # a code span around the value; its opening backtick is no part of the value
        value = value[:-1].rstrip(".,;")
        value = value[1:] if value[:1] == "`" else value
    if value[-1:] in (")", "]") and ("(" if value[-1] == ")" else "[") not in value:
        value = value[:-1].rstrip(".,;")
    if value[:1] + value[-1:] in WRAP_PAIRS:
        value = value[1:-1]
    return value


def boolean_run_is_code(found):
    """True when the value after a password word is a minified boolean and everything after it on the line, up to a
    closer (`}` `)` `]`) or the line end, is `,name:` / `;name=` members that each hold a boolean. A word after the
    boolean (`!0,hunter2`, `!0 hunter2`) or a member with any other value (`!0,pwd:hunter2`) may be the secret, so it is
    not code. Text after the closer is no part of this match: a later password word there is a match of its own."""
    start = JS_BOOLEAN_START.match(found.group(2))
    if not start:
        return False
    rest = found.group(2)[start.end():] + REST_OF_LINE.match(found.string, found.end(2)).group(0)
    while True:
        rest = rest.lstrip()
        if not rest.strip(".,;") or rest[0] in "})]":
            return True
        member = JS_RUN_NEXT.match(rest)
        if not member:
            return False
        rest = rest[member.end():]
        start = JS_BOOLEAN_START.match(rest)
        if not start:
            return False
        rest = rest[start.end():]


def rest_is_prose(rest):
    """True when `rest` is plain prose after a password value and holds no second value after a separator."""
    if not PROSE_REST.fullmatch(rest):
        return False
    after_separator = False
    for token in PROSE_TOKEN.findall(rest):
        token = token.lower()
        if token in PROSE_SEPARATORS or token in ";,":
            after_separator = True
        elif after_separator and token not in PROSE_FUNCTION_WORDS:
            return False
    return True


def password_is_no_secret(found):
    """True when the value after a password word is a plain word, a mask or a placeholder, or `found` is
    `PWD=<path>`, or a minified boolean run is code; otherwise nothing but blanks or plain prose follows the value."""
    if boolean_run_is_code(found):
        return True
    rest = REST_OF_LINE.match(found.string, found.end(2)).group(0)
    if rest.strip() and not rest_is_prose(rest):
        return False
    value = bare_value(found.group(2))
    if found.group(1) == SHELL_PWD and SHELL_PATH.fullmatch(value):
        return True
    return (value.lower() in PLAIN_VALUES or value in JS_BOOLEANS or bool(MASK_VALUE.fullmatch(value))
            or bool(PLACEHOLDER_VALUE.fullmatch(value)))


def email_is_no_person(found):
    """True when the address is a no-reply mailbox, or `git@<public git host>` in an ssh remote."""
    local, _, host = found.group(0).rpartition("@")
    if NO_REPLY_NAME.fullmatch(local):
        return True
    return (local == "git" and host.lower() in PUBLIC_GIT_HOSTS
            and found.string[found.end():found.end() + 1] in (":", "/"))


def long_value_is_no_secret(found):
    """True when `found` is a LONG_CREDENTIAL_VALUE match whose value lacks a letter or a digit."""
    value = found.group("value")
    return not (any(c.isdigit() for c in value) and any(c.isalpha() for c in value))


WORD_SEGMENT = re.compile(r"[a-z]+|[A-Z]+|[A-Z][a-z]+")  # one word in lower case, upper case or capitalised
LOWER_WORD = re.compile(r"[a-z]+")  # a separated part in lower case only
# Four or more consonants in a row; `y` counts as a consonant here. It finds `nstr` in `monstrous`.
CONSONANT_RUN = re.compile(r"[b-df-hj-np-tv-z]{4,}", re.I)
LOWER_RUN = re.compile(r"[b-df-hj-np-tv-z]{5,}", re.I)  # five or more consonants in a row, `y` among them
HAS_VOWEL = re.compile(r"[aeiouy]", re.I)  # one vowel, `y` among them, so `lynx` and `sync` hold one


def letters_are_words(value):
    """True when a letters-only value reads as words. Every part split on `-` or `_` (empty parts dropped) must be one
    word in one case form (lower case, upper case or capitalised), or the value is refused. Then one of two checks runs.
    Separated form: the value splits on `-` or `_` into two or more parts, none empty, all lower case
    (`tight-compact`, `page_length_limit`). It passes when every part of four or more letters holds a vowel
    (`a e i o u y`) and no part holds five or more consonants in a row (`y` counts as a consonant in the run). A part of
    one to three letters needs no vowel, so `db-connection-pool` and `btn-primary-hover` pass. It skips the vowel share.
    `kqzv_bxjw_tmrl` is refused. Any other value (one part, a mixed case, or an empty part as in `tight--compact`): at
    least 30% of its letters are vowels (`a e i o u`) and no run of four or more consonants across the joined letters.
    `REPLACE_WITH_YOUR_KEY` and `infrastructure` pass. Random single-part lower-case letters with enough vowels still pass."""
    parts = [p for p in re.split(r"[_-]", value) if p]
    letters = "".join(parts)
    if not (letters and all(WORD_SEGMENT.fullmatch(p) for p in parts)):
        return False
    separated = re.split(r"[_-]", value)
    if len(separated) > 1 and all(LOWER_WORD.fullmatch(p) for p in separated):
        # A part of 1-3 letters (`db`, `pr`, `btn`) needs no vowel.
        return all((len(p) <= 3 or HAS_VOWEL.search(p)) and not LOWER_RUN.search(p) for p in separated)
    return (sum(c in "aeiouAEIOU" for c in letters) * 10 >= len(letters) * 3
            and not CONSONANT_RUN.search(letters))


# A name made of lower-case words joined by hyphens. A part holds a digit only as a version: one letter and one or two
# digits (`automations-v3-review`). `ab12` and `abcdefgh1` read as random, so they are no part of a name.
HYPHEN_WORDS = re.compile(r"(?:[a-z]+|[a-z]\d{1,2})(?:-(?:[a-z]+|[a-z]\d{1,2}))+")
# A vendor-style key made of words: a 2 or 3 letter vendor prefix, an environment word, then a last part with a digit
# (`sk-live-ab12`, `pk-test-ab12`). It is a key shape, so the hyphen-words path must not pass it.
VENDOR_KEY = re.compile(r"[a-z]{2,3}-(?:live|test|prod|dev|stage|staging|sandbox)(?:-[a-z]+\d{0,2})*-[a-z]*\d\w*")
VALUE_END = frozenset("\"'`,;)}] \t\r\n")


def credential_is_no_secret(found):
    """True when `found` names no secret. A LONG_CREDENTIAL_VALUE match passes when its value lacks a letter or a
    digit. A match of the other `credential-name` shape passes when a `:` set a letters-only value that reads as
    words (an `=` assigns, so it never passes there), or when any separator set a whole value of lower-case words
    joined by hyphens, as a localStorage key name is."""
    if found.re is LONG_CREDENTIAL_VALUE:
        return long_value_is_no_secret(found)
    value = found.group("letters")
    if value:
        return found.group("sep") == ":" and letters_are_words(value)
    value = found.group("mixed")
    if value and JS_KEYWORD_VALUE.fullmatch(value):
        return True
    return (bool(value) and HYPHEN_WORDS.fullmatch(value) is not None
            and VENDOR_KEY.fullmatch(value) is None
            and found.string[found.end():found.end() + 1] in VALUE_END | {""}
            and letters_are_words(re.sub(r"\d", "", value)))


# A match of these shapes can still name no secret and no person. Every other shape refuses on any match.
NO_SECRET_MATCH = {"password": password_is_no_secret, "email": email_is_no_person, "credential-name": credential_is_no_secret}


def kinds_in(text):
    """The kinds of secret or personal data that `text` has the shape of, each once."""
    found = list(dict.fromkeys(  # address has three shapes: report its kind once
        name for name, shape in SECRET_SHAPES
        if any(not NO_SECRET_MATCH.get(name, lambda match: False)(m) for m in shape.finditer(text))))
    if is_phone(text):
        found.append("phone")
    return found


def plain_key(key):
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def scan(node, path, out):
    """Append (path, kind) to `out` for each string value, each key and each phone-length integer of the parsed JSON
    `node`. The path of a find in a key names that key as <redacted>, so a find's line never holds its value."""
    if isinstance(node, str):
        out.extend((path, kind) for kind in kinds_in(node))
    elif isinstance(node, int) and not isinstance(node, bool):
        if len(str(abs(node))) in PHONE_DIGITS:
            out.append((path, "phone"))
    elif isinstance(node, list):
        for number, child in enumerate(node):
            scan(child, "%s[%d]" % (path, number), out)
    elif isinstance(node, dict):
        for key, child in node.items():
            hit = kinds_in(key)
            here = "%s.%s" % (path, "<redacted>" if hit else plain_key(key))
            out.extend((here, kind) for kind in hit)
            scan(child, here, out)


def canonical(data):
    """The text a copy holds for `data`: sorted keys, two-space indent, a final newline."""
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def script_safe(text):
    """JSON `text` with each `<` written as the escape \\u003c, so it pastes into a <script> block as is: no value can
    close the script, and the text parses to the same values. A `<` in JSON text sits only inside a string."""
    return text.replace("<", "\\u003c")


def load_json(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as err:
        raise Stop("unknown - %s is not one JSON doc (%s)" % (label, type(err).__name__), UNKNOWN)


def docs_in(folder, label):
    """{doc_id: parsed JSON} of the `<doc_id>.json` files in `folder`. Anything but the marker is unknown: a doc that
    is skipped would be deleted from the copy as if it were gone."""
    found = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name == MARKER and os.path.isfile(path):
            continue
        if not (os.path.isfile(path) and name.endswith(".json") and len(name) > len(".json")):
            raise Stop("unknown - %s/%s is not a <doc_id>.json file" % (label, name), UNKNOWN)
        found[name[:-len(".json")]] = load_json(path, "%s/%s" % (label, name))
    return found


def read_page(page_path):
    """(bytes, text) of the page at `page_path`. The bytes are what lands in the copy; the text is what is scanned."""
    try:
        with open(page_path, "rb") as handle:
            raw = handle.read()
        return raw, raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise Stop("unknown - the page cannot be read (%s)" % type(err).__name__, UNKNOWN)


def design_data(text):
    """The parsed JSON of the one designData block in the page `text`."""
    try:
        start, end = splice.design_span(text, "the page")
    except SystemExit as err:
        raise Stop("unknown - %s" % str(err).replace(", so nothing was written.", ""), UNKNOWN)
    element = text[start:end]
    body = element[element.index(">") + 1:element.rindex("</")]
    try:
        return json.loads(body)
    except ValueError:
        raise Stop("unknown - the page's designData block is not JSON", UNKNOWN)


def supporting_files(folder):
    """{relative path: bytes} of each file under `folder`, a page's supporting files; {} when there is none."""
    found = {}
    for here, _dirs, names in os.walk(folder):
        for name in names:
            with open(os.path.join(here, name), "rb") as handle:
                found[os.path.relpath(os.path.join(here, name), folder).replace(os.sep, "/")] = handle.read()
    return found


def page_kinds(text):
    """`kinds_in` for page text, a supporting file or its name: a version pin such as `react@18.3.1` and a retina
    image name are not emails."""
    return kinds_in(RETINA_NAME.sub("@", VERSION_PIN.sub("@", text)))


def scan_text(label, text, finds):
    """Append (label, "$", kind) to `finds` for each kind of find in `text`, a page or a supporting text file."""
    finds.extend((label, "$", kind) for kind in page_kinds(text))


def file_text(raw):
    """The text of a supporting file to scan: UTF-8, else latin-1 (so a cp1252 note is read). None for a binary
    file: one with a NUL byte, whatever its name, so a text file under an image or font name is scanned."""
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def refuse(finds, prefix=""):
    for label, path, kind in finds:
        print("%s%s %s %s" % (prefix, label, path, kind))
    raise Stop("refused - %d find(s)" % len(finds), REFUSED)


def existing(out, collections=COLLECTIONS):
    """{relative path: bytes} of each doc file the copy holds in a folder of `collections`."""
    found = {}
    for name in collections:
        folder = os.path.join(out, name)
        if os.path.isdir(folder):
            for file in os.listdir(folder):
                if file.endswith(".json"):
                    with open(os.path.join(folder, file), "rb") as handle:
                        found["%s/%s" % (name, file)] = handle.read()
    return found


def fetched_docs(fetched, collections):
    """{collection: {doc id: data}} read from the fetched folder; Stop (unknown) when a folder or its marker is missing."""
    docs = {}
    for name in collections:
        folder = os.path.join(fetched, name)
        if not os.path.isdir(folder):
            raise Stop("unknown - the fetched folder has no %s folder" % name, UNKNOWN)
        if not os.path.isfile(os.path.join(folder, MARKER)):
            raise Stop("unknown - %s has no %s marker, so the fetch may have stopped early" % (name, MARKER), UNKNOWN)
        docs[name] = docs_in(folder, name)
    return docs


def picture_checks(page, docs):
    """([held item lines], the `checks unknown: <why>` line or None) for the fetched docs against the page file `page`."""
    held, why = page_check.check_items(page, docs["items"], docs.get("answers", {}))
    return ["held item %s: %s" % (n, sentence) for n, sentence in held], ("checks unknown: " + why) if why else None


def check_lacks(collections):
    """The collections of `collections` that the picture check needs and that are missing (items, answers), in that order."""
    return [name for name in CHECK_COLLECTIONS if name not in collections]


def export(fetched, out, page, allow_empty, collections=COLLECTIONS, prefix="", design=True, files=None):
    """(verdict, `checks unknown` line or None, held item lines). The picture check runs after the copy is written, on the
    waiting page's own export only (`design`), and never on a refused or unknown run."""
    docs = fetched_docs(fetched, collections)

    have = existing(out, collections)
    for name in collections:
        kept = [label for label in have if label.startswith(name + "/")]
        if not docs[name] and kept and name not in allow_empty:
            raise Stop("unknown - %s is empty but the copy holds %d doc(s) of it; pass --allow-empty %s if it emptied"
                       % (name, len(kept), name), UNKNOWN)

    want = {}
    finds = []
    for name in collections:
        for doc_id, data in docs[name].items():
            hits = [("$id", kind) for kind in kinds_in(doc_id)]
            label = "%s/%s.json" % (name, "<redacted>" if hits else doc_id)
            scan(data, "$", hits)
            finds.extend((label, path, kind) for path, kind in hits)
            want["%s/%s.json" % (name, doc_id)] = canonical(data).encode("utf-8")
    if page:
        raw, text = read_page(page)
        label = "%s/%s" % (PAGE_FOLDER, PAGE_FILE)
        if design:
            data = design_data(text)
            found = []
            scan(data, "$", found)
            finds.extend(("%s/%s" % (PAGE_FOLDER, DESIGN_FILE), path, kind) for path, kind in found)
            want["%s/%s" % (PAGE_FOLDER, DESIGN_FILE)] = canonical(data).encode("utf-8")
        scan_text(label, text, finds)
        want[label] = raw
    for rel, raw in (files or {}).items():
        text = file_text(raw)
        name_kinds = page_kinds(rel)
        label = "%s/%s/%s" % (PAGE_FOLDER, FILES_FOLDER, "<redacted>" if name_kinds else rel)
        finds.extend((label, "$name", kind) for kind in name_kinds)
        if text is not None:
            scan_text(label, text, finds)
        want["%s/%s/%s" % (PAGE_FOLDER, FILES_FOLDER, rel)] = raw
    if finds:
        refuse(finds, prefix)  # before any write, so a refused run leaves the copy as it was

    changed = 0
    for label, raw in want.items():
        target = os.path.join(out, *label.split("/"))
        if label in have:
            old = have[label]
        elif os.path.isfile(target):  # the page and its files are not in a collection folder
            with open(target, "rb") as handle:
                old = handle.read()
        else:
            old = None
        if old != raw:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(raw)
            changed += 1
    for label in have:
        if label not in want:
            os.remove(os.path.join(out, *label.split("/")))
            changed += 1
    unknown, held = None, []
    lacking = check_lacks(collections) if design else []
    if lacking:  # the check needs both: with no answers it would hold an item the page draws as answered
        unknown = "checks unknown: collections lack " + ", ".join(lacking)
    elif design:
        if page:
            held, unknown = picture_checks(page, docs)
        elif page_check.pictured_items(docs["items"])[0]:  # a pictured item and no page: the check cannot run
            unknown = "checks unknown: no page file"
    return ("changed %d" % changed if changed else "same"), unknown, held


def export_all(root, fetched, worktree, allow_empty, account=None):
    """Export each registry artifact of the repo at `root`; print one line per artifact; the exit code."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
    sys.path.insert(1, os.path.join(os.path.expanduser("~"), ".claude", "lint"))
    import layout  # --all mode only: a single export and the rebuild run with no lint/ beside them
    try:
        entries = layout.artifacts(root)
    except layout.LayoutError as err:
        raise Stop("unknown - the artifacts registry cannot be read: %s" % err, UNKNOWN)
    if not entries:
        raise Stop("unknown - %s has no artifacts registry entry to export" % root, UNKNOWN)
    if account is not None and account not in {entry["account"] for entry in entries}:
        # a mistyped or empty label would otherwise skip every entry and still exit 0, which reads as a clean copy
        raise Stop("unknown - --account %r matches no registry entry's account, so nothing was exported" % account, UNKNOWN)
    worst, held_any = 0, False
    for entry in entries:
        name = entry["id"]
        if entry["export"] is False:  # held in the registry, never exported: no folder needed, nothing written
            print("%s: skipped - no export" % name)
            continue
        if account is not None and entry["account"] != account:  # a page this session cannot read: no folder needed
            print("%s: skipped - account %s" % (name, entry["account"]))
            continue
        folder = os.path.join(fetched, name)
        page = os.path.join(folder, PAGE_FILE)
        files = os.path.join(folder, FILES_FOLDER)
        try:
            if not os.path.isdir(folder):
                raise Stop("unknown - the fetched folder has no %s folder" % name, UNKNOWN)
            if not entry["collections"] and not os.path.isfile(page):  # a page-only entry has nothing else to export, so "same" would hide a failed fetch
                raise Stop("unknown - the fetched folder has no %s, and this page-only entry exports nothing else" % PAGE_FILE, UNKNOWN)
            verdict, unknown, held = export(folder, os.path.join(worktree, *entry["export"].split("/")),
                             page if os.path.isfile(page) else None, allow_empty, tuple(entry["collections"]), "%s: " % name,
                             entry["role"] == layout.WAITING_ROLE, supporting_files(files) if os.path.isdir(files) else None)
            code = UNKNOWN if entry["role"] == layout.WAITING_ROLE and check_lacks(entry["collections"]) else 0
        except Stop as stop:
            verdict, unknown, held, code = str(stop), None, [], stop.code
        except Exception as err:  # one artifact's crash must not hide the verdict of the others
            verdict, unknown, held, code = "unknown - the run crashed (%s)" % type(err).__name__, None, [], CRASH
        if unknown:  # before the verdict, so the verdict stays the last line of the artifact
            print("%s: %s" % (name, unknown))
        print("%s: %s" % (name, verdict))
        for line in held:
            print("%s: %s" % (name, line))
        held_any = held_any or bool(held)
        worst = max(worst, code)
    return worst or (HELD if held_any else 0)  # a held item is 4 only when nothing worse (1, 2 or 3) happened


def check_only(fetched, page):
    """--check: the export's picture checks on the fetched items and the page file; nothing is written. The exit code."""
    read_page(page)  # a page that is not one readable file is unknown, as in an export
    held, unknown = picture_checks(page, fetched_docs(fetched, CHECK_COLLECTIONS))
    for line in held:
        print(line)
    if unknown:
        print(unknown)
    if held:
        return HELD
    if unknown:
        return CRASH  # exit 3: the checks could not run
    print("checks pass")
    return 0


def entry_bytes(entry):
    """The bytes `entry` takes inside a batch file, which is `canonical` of a list: two-space indent on each line."""
    text = json.dumps(entry, sort_keys=True, indent=2)
    return len(text) + 2 + 2 * text.count("\n")  # ensure_ascii is on, so a character is a byte


def batch_bytes(count, entries_total):
    """A batch file's size: "[\\n", the entries joined by ",\\n", "\\n]" and the final newline."""
    return 3 + 2 * count + entries_total


def read_copy(waiting, collections):
    """The `set` entries of each doc in the copy `waiting`, in sorted folder then doc_id order. `page/` is no doc."""
    entries = []
    if os.path.isdir(waiting):
        for name in sorted(os.listdir(waiting)):
            folder = os.path.join(waiting, name)
            if name == PAGE_FOLDER:
                continue
            if name not in collections or not os.path.isdir(folder):
                raise Stop("unknown - %s/%s is neither a collection folder nor %s/" % (waiting, name, PAGE_FOLDER), UNKNOWN)
            for doc_id, data in docs_in(folder, name).items():
                entries.append({"op": "set", "collection": name, "doc_id": doc_id, "data": data})
    if not entries:
        raise Stop("unknown - %s holds no docs" % waiting, UNKNOWN)
    return entries


def write_batches(entries, batches):
    """Split `entries` into batch-NNN.json files under `batches`: at most BATCH_SIZE entries and under BATCH_BYTES each.
    A doc over the cap is unknown, and nothing is written. The one home of the split, for --rebuild and --merge."""
    pieces, piece, total = [], [], 0
    for entry in entries:
        size = entry_bytes(entry)
        if batch_bytes(1, size) >= BATCH_BYTES:
            raise Stop("unknown - %s/%s is over the %d byte batch cap" % (entry["collection"], entry["doc_id"], BATCH_BYTES), UNKNOWN)
        if piece and (len(piece) == BATCH_SIZE or batch_bytes(len(piece) + 1, total + size) >= BATCH_BYTES):
            pieces.append(piece)
            piece, total = [], 0
        piece.append(entry)
        total += size
    pieces.append(piece)

    os.makedirs(batches, exist_ok=True)
    for number, piece in enumerate(pieces, 1):
        with open(os.path.join(batches, "batch-%03d.json" % number), "w", encoding="utf-8", newline="") as handle:
            handle.write(canonical(piece))
    return len(pieces)


def rebuild(waiting, batches, collections=COLLECTIONS):
    entries = read_copy(waiting, collections)
    return "batches %d docs %d" % (write_batches(entries, batches), len(entries))


def live_docs(live, collections):
    """{collection: {doc_id: data}} of the live page's fetched folder. Each collection needs its folder and marker: a
    fetch cut short would make its missing docs look absent, and a merge would `set` over them."""
    if not os.path.isdir(live):
        raise Stop("unknown - the live folder %s is missing" % live, UNKNOWN)
    for name in sorted(os.listdir(live)):
        if name not in collections or not os.path.isdir(os.path.join(live, name)):
            raise Stop("unknown - %s/%s is not a collection folder" % (live, name), UNKNOWN)
    held = {}
    for name in collections:
        folder = os.path.join(live, name)
        if not os.path.isdir(folder):
            raise Stop("unknown - the live folder has no %s folder" % name, UNKNOWN)
        if not os.path.isfile(os.path.join(folder, MARKER)):
            raise Stop("unknown - live %s has no %s marker, so the fetch may have stopped early" % (name, MARKER), UNKNOWN)
        held[name] = docs_in(folder, name)
    return held


def number_of(data):
    """The `n` of an item, or None when it has none that is a whole number."""
    n = data.get("n") if isinstance(data, dict) else None
    return n if isinstance(n, int) and not isinstance(n, bool) else None


def renumber(fresh, entries, held):
    """The entries in `fresh` with each item whose `n` is taken given the next free `n` above the highest in the live
    page or the copy, in sorted doc_id order, and its answer given the same `n` and its item's id. (entries, count of
    items moved, {old n as a string: new n})."""
    taken = {number_of(data) for data in held["items"].values()} - {None}
    highest = max([n for n in (number_of(e["data"]) for e in entries if e["collection"] == "items") if n is not None]
                  + list(taken), default=0)
    moved, numbers = {}, {}
    for entry in sorted((e for e in fresh if e["collection"] == "items"), key=lambda e: e["doc_id"]):
        n = number_of(entry["data"])
        if n is None:
            continue
        if n in taken:
            highest += 1
            numbers.setdefault(str(n), highest)
            n = highest
            moved[entry["doc_id"]] = (n, entry["doc_id"])
        taken.add(n)
    result = []
    for entry in fresh:
        move = moved.get(entry["doc_id"])
        if move and entry["collection"] == "items":
            entry = dict(entry, data=dict(entry["data"], n=move[0]))
        elif move and entry["collection"] == "answers":
            entry = dict(entry, data=dict(entry["data"], n=move[0], item=move[1]))
        result.append(entry)
    return result, len(moved), numbers


def merged_design(copy, live_page):
    """(the live page's designData plus each copy key it lacks, count of keys added), or (None, 0) when the copy holds no
    page/designData.json. A copy with designs needs the live page's html, whose block must hold a JSON object."""
    path = os.path.join(copy, PAGE_FOLDER, DESIGN_FILE)
    if not os.path.isfile(path):
        return None, 0
    theirs = load_json(path, "%s/%s" % (PAGE_FOLDER, DESIGN_FILE))
    if not live_page:
        raise Stop("unknown - the copy holds %s/%s: pass --live-page, the live page's html" % (PAGE_FOLDER, DESIGN_FILE), UNKNOWN)
    ours = design_data(read_page(live_page)[1])
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        raise Stop("unknown - the live page's designData and the copy's are not both JSON objects", UNKNOWN)
    added = {key: value for key, value in theirs.items() if key not in ours}
    return dict(ours, **added), len(added)


def merge(copy, live, batches, collections=COLLECTIONS, live_page=None):
    """Batches of `set` entries for each doc of the repo copy that the live page lacks, the map of renumbered `n` and the
    merged designData. The live page wins. A copy answer is kept when the live page holds its item."""
    entries = read_copy(copy, collections)
    held = live_docs(live, collections)
    live_items = held.get("items", {})
    fresh = [e for e in entries if e["doc_id"] not in held[e["collection"]]
             and not (e["collection"] == "answers" and e["doc_id"] in live_items)]
    kept = len(entries) - len(fresh)
    if not fresh:
        raise Stop("unknown - the live page already holds all %d doc(s) of the copy; nothing to write" % len(entries), UNKNOWN)
    moved, numbers = 0, {}
    if "items" in collections:
        fresh, moved, numbers = renumber(fresh, entries, held)
    design, added = merged_design(copy, live_page)
    count = write_batches(fresh, batches)
    with open(os.path.join(batches, "renumbered.json"), "w", encoding="utf-8", newline="") as handle:
        handle.write(canonical(numbers))
    if design is not None:
        with open(os.path.join(batches, DESIGN_FILE), "w", encoding="utf-8", newline="") as handle:
            handle.write(script_safe(canonical(design)))
    return "batches %d docs %d kept-live %d renumbered %d designs %d" % (count, len(fresh), kept, moved, added)


def main(argv):
    ap = argparse.ArgumentParser(description="Copy the waiting page's database into the repo, or build batches back from it.")
    ap.add_argument("--fetched", help="the folder `ArtifactData list` saved, one folder per collection")
    ap.add_argument("--out", help="the waiting-data folder to mirror into")
    ap.add_argument("--page", help="the fetched page.html, for its designData block")
    ap.add_argument("--allow-empty", action="append", default=[], metavar="COLLECTION",
                    help="a collection that really emptied, so its docs leave the copy")
    ap.add_argument("--all", help="the repo root whose artifacts registry lists each artifact to export")
    ap.add_argument("--worktree", help="with --all: the record branch worktree each artifact's export path is under")
    ap.add_argument("--check", action="store_true", help="with --fetched and --page: run the picture checks only, write nothing")
    ap.add_argument("--account", help="with --all: export only the entries of this account label; skip the rest")
    ap.add_argument("--rebuild", help="the waiting-data folder to read batches from")
    ap.add_argument("--batches", help="the folder to write batch-NNN.json into")
    ap.add_argument("--merge", help="the repo copy whose docs the live page lacks are batched")
    ap.add_argument("--live", help="with --merge: the folder `ArtifactData list` saved from the live page, markers included")
    ap.add_argument("--live-page", help="with --merge: the live page's fetched html, for its designData block")
    ap.add_argument("--collections", nargs="+", metavar="NAME",
                    help="with --rebuild or --merge: the collection folders to allow, in place of the waiting page's five")
    args = ap.parse_args(argv)
    if args.collections is not None and not (args.rebuild or args.merge):
        ap.error("--collections goes with --rebuild or --merge")
    for name in args.collections or ():
        if not COLLECTION_SLUG.fullmatch(name):
            ap.error("--collections names are slugs: letters, digits, _ and -, starting with a letter or digit: %r" % name)
        if name == PAGE_FOLDER:
            ap.error("--collections cannot name %r: that folder holds the page and its files" % PAGE_FOLDER)
    all_mode = bool(args.all or args.worktree)
    merge_mode = bool(args.merge or args.live)
    export_mode = bool(args.out or args.page or (args.fetched and not all_mode and not merge_mode))
    rebuild_mode = bool(args.rebuild or (args.batches and not merge_mode))
    if args.live_page and not args.merge:
        ap.error("--live-page goes with --merge")
    if merge_mode and not (args.merge and args.live and args.batches):
        ap.error("--merge needs --live DIR and --batches DIR: --merge DIR --live DIR --batches DIR")
    if [all_mode, export_mode, rebuild_mode, merge_mode].count(True) != 1 or (all_mode and not (args.all and args.fetched and args.worktree)) \
            or (export_mode and not (args.fetched and args.out) and not args.check) or (rebuild_mode and not (args.rebuild and args.batches)):
        ap.error("use --fetched DIR --out DIR [--page FILE], or --all ROOT --fetched DIR --worktree DIR, or --rebuild DIR --batches DIR, or --merge DIR --live DIR --batches DIR")
    if args.account is not None and not all_mode:
        ap.error("--account goes with --all")
    if args.check:  # after the --account usage error, so a misused --account fails as it does without --check
        if all_mode or rebuild_mode or args.out or not (args.fetched and args.page):
            ap.error("--check takes --fetched DIR --page FILE and nothing else")
        try:
            return check_only(args.fetched, args.page)
        except Stop as stop:
            print(str(stop))
            return stop.code
        except Exception as err:
            print("unknown - the run crashed (%s)" % type(err).__name__)
            return CRASH
    if export_mode and any(name not in COLLECTIONS for name in args.allow_empty):
        ap.error("--allow-empty names one of: %s" % ", ".join(COLLECTIONS))
    try:
        if all_mode:
            return export_all(os.path.abspath(args.all), args.fetched, args.worktree, args.allow_empty, args.account)
        unknown, held = None, []
        if export_mode:
            verdict, unknown, held = export(args.fetched, args.out, args.page, args.allow_empty)
        elif merge_mode:
            verdict = merge(args.merge, args.live, args.batches, tuple(args.collections or COLLECTIONS), args.live_page)
        else:
            verdict = rebuild(args.rebuild, args.batches, tuple(args.collections or COLLECTIONS))
    except Stop as stop:
        print(str(stop))
        return stop.code
    except Exception as err:  # a crash is unknown, never a silent pass or a traceback the reader scrolls past
        print("unknown - the run crashed (%s)" % type(err).__name__)
        return CRASH
    if unknown:  # before the verdict, so the verdict stays the last line (hooks/feedback_guard.py reads `same` on any line)
        print(unknown)
    print(verdict)
    for line in held:
        print(line)
    return HELD if held else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
