"""Fixture suite for export_page.py. Run: python3 skills/waiting-page/test_export_page.py

EXPORT_PAGE_UNDER_TEST names the script to run (default: export_page.py beside this file), so the same
cases run red against a checkout that lacks it.

Secret-shaped values are joined at run time from parts. No token-shaped literal sits in this source, so a
secret scanner that reads the committed text finds none.

Contract the page cases assume (the builder builds to it):
  --page FILE, one export. The page's bytes land at <out>/page/page.html, byte-identical (CRLF and non-ASCII
    kept). designData still lands at page/designData.json. The page is scanned as text with the same shapes as
    the docs, before any write. A find refuses the whole export: `refused - N find(s)`, exit 1, nothing written.
    A CDN script tag such as react@18.3.1 is not a find; an email address in the text is.
    A second run with the same page prints `same` and rewrites no file (the mtime stays).
    A page changed outside designData, with the same designData, prints `changed 1`.
    A mockup change writes two files, designData.json and page.html, so it prints `changed 2`.
    A page with no designData block, or two, stays `unknown`, exit 2.
  --all. Each entry folder's page.html, for any role, lands at <export path>/page/page.html. Its files/<path>
    land byte-identical at <export path>/page/files/<path>. The waiting page exports to waiting/, any other
    artifact to artifacts/<id>/. Each file written counts one in `changed N`. A find in an artifact's page, or in a
    supporting file's name or text, refuses only that artifact: exit 1, its copy unchanged, and the other artifacts
    still export. A supporting file that is not UTF-8 is scanned as cp1252 text, so a cp1252 note holding an email
    refuses. A file is binary only with a NUL byte, whatever its name: a binary file with no shape in it exports, and a
    text file under an image or font name is scanned.
  --all, a page-only entry (`collections` []) exports its page and files and no database.
  --all --account LABEL. An entry whose account differs prints `<id>: skipped - account <its account>`, needs no fetched
    folder, writes nothing and exits 0 for it. Without the flag every entry exports as before.
    A LABEL no registry entry holds, the empty label included, prints one `unknown` line that names the label, writes
    nothing, exits 2.
  --all, a page-only entry whose fetched folder holds no page.html prints `<id>: unknown - ...` that names page.html,
    writes nothing for it, and the run exits 2.
  Retina names are not emails: `logo@2x.png`, as a file name or in page text, exports; `jane@2x.com` refuses.
  Digit-led domains are emails: jane@1st.example.com, jane@12.34.example.com and jane@1.2.3.com refuse in page text.
  URL credentials refuse on an IP host as on a host name: postgres://app:<password>@10.0.0.5:5432/db refuses; an IP
    host with no credentials passes.
  --rebuild DIR --batches OUT --collections NAME [NAME ...]. The named collections are the only folders allowed besides
    page/, and a batch entry's `collection` is its folder name. A named collection with no folder is empty. A folder not
    named is unknown, exit 2, even one of the five waiting collections. Without --collections the five are allowed.
    --collections without --rebuild, or a name that is not a collection slug, is a usage error: exit 2, an argparse
    `error:` line, nothing written. The error for --collections without --rebuild names --rebuild.
  --merge COPY --live LIVE --batches OUT [--collections NAME ...] [--live-page PATH]. COPY holds the --rebuild layout.
    LIVE holds the --fetched layout: one folder per collection, each with its marker. OUT gets batch-NNN.json files of
    `set` entries, one for each COPY doc whose (collection, doc_id) LIVE lacks. A doc LIVE holds is never written. A copy
    answer (answers/<id>) is not written either when LIVE holds items/<id>: the live page wins on that item, open or
    answered. Batches follow --rebuild: at most 50 entries and 900,000 bytes each, and a doc over the cap is unknown. A
    copied item whose n a live item holds, or an earlier written copied item holds, takes the next free n above the highest
    n in either folder. "Earlier" is the sorted doc_id order. The item's answer (answers/<doc_id>, with `item` set to the
    item's id) takes the same n, so a page grant still matches. OUT/renumbered.json maps each old n to its new n, with
    string keys, and is written even when empty. It holds items only. `renumbered` counts items, not answers.
    `kept-live` counts the COPY docs that LIVE holds, and each answer kept for its live item. The last stdout line is
    `batches K docs N kept-live S renumbered R designs D`, exit 0. D counts the design keys added, and is 0 when the copy
    has no designData. Designs: when COPY holds page/designData.json, --live-page PATH (the live page's fetched html) is
    required. OUT/designData.json then holds the live page's designData plus each copy key that LIVE lacks, and the live
    value wins a shared key. Without --live-page, such a copy is unknown, exit 2. Unknown, exit 2: a missing or empty
    COPY, a missing LIVE, a LIVE collection with no .complete marker (a cut-short fetch), a folder in either that is not a
    collection (or a --collections name), a live page with no designData block (when the copy has designs), or nothing
    left to write. The COPY needs no marker. --collections works as with --rebuild. A usage error, exit 2: --merge without
    --live or --batches.
  Verdict words: `changed N`, `same`, `refused` (exit 1), `unknown` (exit 2), and a crash (exit 3, one line).
  Not pinned here: whether a supporting file no longer fetched is deleted.
  Picture checks. Each fetched item that carries a
    picture (a `designs` list or an option `design`) and is an open decision (not closed, not a ruling, not answered)
    is checked by the page's own check, check_designs.mjs. A miss prints `held item <n>: <the page's sentence>` after
    the verdict line and exits 4; the copy is still written. A check that cannot run prints one
    `checks unknown: <why>` line, the copy is written, and the exit code is as without checks. Never a pass line.
    --all holds the same way in the waiting-page entry, with the artifact id before the line.
  --check: `export_page.py --check --fetched DIR --page FILE` runs the same item checks
    and writes nothing. A held item prints its `held item <n>: <sentence>` line and exits 4; a clean run prints one line
    `checks pass` and exits 0; a check that cannot run prints `checks unknown: <why>` and exits 3.
  --all, a waiting-page entry whose own `collections` lacks `items` or `answers`: `<id>: checks unknown: collections lack
    <name>`, the copy written, exit 2, and no item held for that entry (an unread answers collection holds answered items).
  The picture checks of one run share one time budget. Items not checked when it runs out print
    `checks unknown: time budget spent, <k> item(s) not checked`; --check exits 3; export keeps its copy and its exit code.
"""
import collections
import contextlib
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CMD = os.environ.get("EXPORT_PAGE_UNDER_TEST") or os.path.join(HERE, "export_page.py")
LINT = os.path.realpath(os.path.join(HERE, "..", "..", "lint"))
sys.path.insert(0, LINT)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
import export_page  # noqa: E402  the in-process budget cases stub page_check's per-run seam
import page_check  # noqa: E402
import _nowindow  # noqa: E402  the answers cases stub its run, the one start of node (page_check imports it from hooks/)

COLLECTIONS = ("items", "answers", "groups", "asks", "meta")
MARKER = ".complete"  # the session touches it in each collection folder after the last list page
ARTIFACT = "https://claude.ai/artifact/RddcgXbB6SvTrFZHPmsvFx"
SENTINEL = 1000000000  # a fixed mtime for a file a run must not rewrite; no clock is read
TAIL = "aB3" * 12  # 36 characters, the body of a GitHub token
TG_TAIL = "aB3" * 11 + "Qz"  # 35 characters, the body of a Telegram bot token
# A line of base64 in an armored PGP key block, built from parts. A key block's header is what the scan keys on; the body
# is only the line after it, with no shape of its own.
PGP_BODY = "mQINBFa3pQ8BEADk7Yq2Rv9Lw1Tn5Hs8" + "Jb4Ke6Fa0Pd3Gu7Mi2Oz5Xr9Ct1Vw8Ny4Qe6Lm"
# Letters only, built from parts: a credential value with no digit. The length rule counts characters, digits or not.
LETTERS_11 = "QwErTyUi" + "OpA"  # one short of the credential length
LETTERS_12 = LETTERS_11 + "s"  # the credential length
LETTERS_14 = "lkjhgfds" + "amnbvc"  # lower case
LETTERS_16 = "xKqPzLmR" + "tWbNvYcH"
CAPS_16 = "QWRTZXLK" + "JHGFDSBN"  # sixteen random capitals, no lower-case run at all
UNDERSCORE_16 = "xKqP_zLm" + "RtWbNvYc"  # sixteen random letters with an underscore, and no lower-case run of three
SUPER_PASSWORD = "supersecret" + "password"  # letters that read as words: a secret after a SECRET_KEY name all the same
FEW_VOWELS_16 = "BCDABCDABCDABCDA"  # sixteen capitals with four vowels and no run of four: fails only the vowel share
LONG_CONSONANT_RUN_16 = "AEIOUBCD" + "FGHJKLMN"  # sixteen capitals with eleven consonants in a row: fails only the run check
CLIENT_LETTERS_16 = "BnMvCxZl" + "KjHgFdSa"
HUMP_AFTER_TWO_16 = "abCdefgh" + "ijklmnop"  # a capital after two lower-case letters: random, not a camelCase word
DESIGN = re.compile(r'(<script type="application/json" id="designData">)(.*?)(</script>)', re.S)
DESIGN_BODY = '{"a": "\\u003cp>mockup\\u003c/p>", "b": "<i>raw</i>"}'
META = {"title": "Queue", "version": 1}
DEEP = "[" * 5000 + "]" * 5000  # nests past the interpreter's recursion limit: a crash, not a verdict
RUN_FOLDER = None  # made in setUpModule
TOKEN = "ghp_" + TAIL  # a GitHub-token shape, built at run time
MAIL = "person.name" + "@" + "example.com"  # a personal-email shape, built at run time
PASSWORD = "hunter2"  # a password value; the URLs below join it at run time, so no credential URL is a literal here
SUP_PASSWORD = "Sup3r" + "S3cret"  # letters, digits and capitals, joined from parts, for the concatenated and templated URL rows
HUNTER_PASSWORD = "Hunter" + "2xx"  # a literal password, joined from parts, for the templated-user URL rows
QUOTE_PASSWORD = "O'" + "Neil2020"  # a literal password that holds a single quote, joined from parts
QUOTE_IN_PASSWORD = 'p"' + "ss"  # a literal password that holds a double quote, joined from parts
DB_IP_URL = "postgres://app:" + PASSWORD + "@10.0.0.5:5432/db"  # credentials on an IP host, with a port
BUILD_IP_URL = "https://svc:" + PASSWORD + "@10.0.0.5/build"  # credentials on an IP host, with no port
DB_NAME_URL = "postgres://app:" + PASSWORD + "@db.example.com:5432/db"  # the control: a host name refuses today
IP_LINK_SNIPPET = '<a href="https://10.0.0.5:5432/db">db</a>\n'  # an IP host with no credentials is not a secret

with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
    PAGE = f.read()
assert len(DESIGN.findall(PAGE)) == 1, "page.html must hold one designData block: the fixture's shape"
DESIGN_ELEMENT = DESIGN.search(PAGE).group(0)
# The fixture page as bytes with a CRLF line and non-ASCII text, so a copy that normalizes either goes red.
PAGE_BYTES = PAGE.replace("<style>", "<!-- café — über -->\r\n<style>", 1).encode("utf-8")
REVISED_PAGE = PAGE.replace("<style>", "<!-- revised note -->\n<style>", 1).encode("utf-8")  # changed outside designData
QUEUE_PAGE = ("<!doctype html>\r\n<html><head><meta charset=\"utf-8\"><title>Queue café</title></head>\r\n"
              "<body><p>Queue page</p></body></html>\r\n").encode("utf-8")  # a page with no designData block
BIG_PAGE = (PAGE + "".join("<p>Row %d of the synthetic page.</p>\n" % n for n in range(1, 25001))).encode("utf-8")  # about 1.2 MB
CDN_SNIPPET = ('<script src="https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js"></script>\n'
               '<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"></script>\n')
PROSE_SNIPPET = ("<p>Don't use /* or // or # here.</p>\n<!-- a note for the reader -->\n"
                 "<script>\nconst s = `line one\nline two`;\n</script>\n")

# Parts of the postal-address and credential-name rows. A credential value is joined from parts, as TAIL is.
STREET = "123 Main Street"
API_VALUE = "abcdefgh" + "12345678"
SESSION_VALUE = "q9W8e7R6" + "t5Y4u3I2"
CLIENT_VALUE = "Zx8Kp2Lm" + "9Qw4Rt7Y"
GLUED_VALUE = "Yt6Nb3Kd9Hj2" + "Pq7W"  # a credential value of letters and digits, built from parts
# Two hundred letters, one 16-letter block repeated 12 times and 8 more: a digit after them sits at offset 200, past a lookahead of 20 characters.
LETTERS_200 = LETTERS_16 * 12 + "xKqPzLmR"
# Three hundred letters, 16 letters repeated 18 times and 12 more, with no digit: only the letters side of the long-value shape reads it.
LETTERS_300 = LETTERS_16 * 18 + LETTERS_12
assert len(LETTERS_300) == 300, "LETTERS_300 must hold 300 letters"
NPM_VALUE = "npm_Ab3Cd5Ef7Gh9Ij1Kl3" + "Mn5"  # an npm token shape, built from parts
PROSE_SECRET = "correcthorsebatterystaple"  # letters only, no digit, symbol or hump: only the prose rule can refuse it
# A digit at index 256 of a credential value: refused, and it must stay refused.
CAP_LAST_DIGIT = "abcdefgh" * 32 + "1"
# A digit with letters before it and no other digit: at index 257, and at index 1000. Refused, wherever the digit sits.
DIGIT_AT_257 = "abcdefgh" * 32 + "a1"
DIGIT_AT_1000 = "abcdefgh" * 125 + "1"
assert CAP_LAST_DIGIT.index("1") == 256 and DIGIT_AT_257.index("1") == 257 and DIGIT_AT_1000.index("1") == 1000, \
    "the digit fixtures must sit at their named indexes"
# 300 digits and no letter, and the same with a letter after them at index 300. The long-value shape refuses a value with a
# letter and a digit, and allows one with a digit and no letter. Only the long-value shape reads past index 256.
DIGITS_300 = "7" * 300
DIGITS_300_THEN_LETTER = DIGITS_300 + "a"
assert DIGITS_300_THEN_LETTER.index("a") == 300, "the letter must sit at index 300, past the short shape's window"
# A scan that re-reads a run from each start position takes about 16 times as long over four times the run; a linear
# scan takes about 4 times. The bound sits between them. RUN_N is the shorter run, the longer run is four times it.
RUN_N = 20000
GROWTH_BOUND = 10
# Hyphenated letters for the words test, built from parts. Each comment names the check the value fails.
TIGHT_COMPACT = "tight-" + "compact"  # a plain option key that passes: each part holds a vowel, and no part has five consonants in a row
ICON_COMPACT = "icon-" + "compact"  # a plain option key that passes: a vowel in each part
PAGE_LENGTH_LIMIT = "page-" + "length-limit"  # a plain option key that passes: `length` has four consonants in a row, one short of the five that refuse
STRENGTH_METER = "strength-" + "meter"  # a plain option key that passes: `strength` has runs of three and four consonants, under the five that refuse
BRIGHT_LIGHTS_CITY = "bright-" + "lights-" + "city"  # a plain option key that passes: `lights` has four consonants in a row, under the five that refuse
TIGHT_SNAKE = "tight_" + "compact"  # the snake_case form passes: each part holds a vowel, and no part has five consonants in a row
PAGE_SNAKE = "page_" + "length_" + "limit"  # the snake_case form passes: no part has five consonants in a row
MIXED_HYPHEN = "QwErTy-" + "UiOpAs"  # mixed case in each part: refused by the word form alone; the vowel rule reads only all-lower values
CONSONANT_HYPHEN = "xkcdqwrt-" + "plmnvbz"  # all-lower, no vowel in either part: refused by the run (eight and seven consonants) and by the vowel rule
UPPER_HYPHEN = "XKQ-ZVB-" + "WTR-PLS"  # upper-case parts with no vowel: refused by the vowel share and by the joined run; the all-lower rules do not reach it
RUN_PART = "aeibcdfgt" + "-uaei"  # a run of six consonants inside one part, with a vowel in each part: refused by that run alone
SHORT_VOWELS = "bbabbab" + "bbabbb"  # three vowels in thirteen letters and no run: fails the vowel share alone
RUN5_HYPHEN = "aeixkcdqo" + "-uaei"  # a run of five consonants inside one part, with a vowel in each part: refused by that run alone
RUN5_UNDERSCORE = "aeixkcdqo" + "_uaei"  # the same run with an underscore: refused by it, as the hyphen twin is
FEW_VOWEL_WORD = "bcdafgh" + "ejklomnp"  # lower case, no separator, three vowels in fifteen letters and no run: fails the share alone
# Each comment names the check the value fails. The vowel rule refuses an all-lower value split on `-` or `_` when a part of
# four or more letters holds no vowel (a, e, i, o, u or y). A part of one to three letters is exempt from it.
VOWELLESS_SNAKE = "kqzv_" + "bxjw_" + "tmrl"  # snake_case, four consonants and no vowel in each part: fails the vowel rule
VOWELLESS_HYPHEN = "kqzv-" + "bxjw-" + "tmrl"  # the hyphen twin, four consonants and no vowel in each of three parts: fails the vowel rule

# (label, the note's value, the text that must never be printed). A dict or a list nests the secret.
RED = [
    ("GitHub token", "ghp_" + TAIL, "ghp_" + TAIL),
    ("GitHub OAuth token", "gho_" + TAIL, "gho_" + TAIL),
    ("GitHub user token", "ghu_" + TAIL, "ghu_" + TAIL),
    ("GitHub server token", "ghs_" + TAIL, "ghs_" + TAIL),
    ("GitHub refresh token", "ghr_" + TAIL, "ghr_" + TAIL),
    ("GitHub fine-grained token", "github_pat_" + "aB3" * 8, "github_pat_" + "aB3" * 8),
    ("Anthropic key", "sk-ant-" + "aB3" * 12, "sk-ant-" + "aB3" * 12),
    ("OpenAI-style key", "sk-proj-" + "aB3" * 10, "sk-proj-" + "aB3" * 10),
    ("AWS key id", "AKIA" + "ABCDEFGHIJKLMNOP", "AKIA" + "ABCDEFGHIJKLMNOP"),
    ("AWS session key id", "ASIA" + "ABCDEFGHIJKLMNOP", "ASIA" + "ABCDEFGHIJKLMNOP"),
    ("Slack token", "xoxb-" + "123456789012-abcdefABCDEF", "xoxb-" + "123456789012-abcdefABCDEF"),
    ("Google API key", "AIzaSy" + "aB3" * 11, "AIzaSy" + "aB3" * 11),
    ("Stripe live key", "sk_live_" + "aB3" * 8, "sk_live_" + "aB3" * 8),
    ("Stripe test key", "sk_test_" + "aB3" * 6, "sk_test_" + "aB3" * 6),
    ("Stripe restricted test key", "rk_test_" + "aB3" * 6, "rk_test_" + "aB3" * 6),
    ("Stripe test key of 16 characters", "sk_test_" + "aB3" * 5 + "a", "sk_test_" + "aB3" * 5 + "a"),
    ("Docker Hub PAT", "dckr_pat_" + "aB3" * 7, "dckr_pat_" + "aB3" * 7),
    ("Docker Hub PAT of 20 characters", "dckr_pat_" + "aB3" * 6 + "aB", "dckr_pat_" + "aB3" * 6 + "aB"),
    # A Telegram token is digits, a colon and 35 characters. In the bot API URL the digits follow `bot` with no word boundary.
    ("Telegram bot token of 10 digits", "1234567890:" + TG_TAIL, "1234567890:" + TG_TAIL),
    ("Telegram bot token after a label", "Bot token: " + "12345678:" + TG_TAIL, "12345678:" + TG_TAIL),
    ("Telegram bot API URL", "https://api.telegram.org/bot" + "123456789:" + TG_TAIL + "/getMe",
     "123456789:" + TG_TAIL),
    ("GitLab token", "glpat-" + "aB3" * 6 + "Qz", "glpat-" + "aB3" * 6 + "Qz"),
    ("PEM private key header", "-----BEGIN " + "RSA " + "PRIVATE KEY-----", "-----BEGIN " + "RSA " + "PRIVATE KEY-----"),
    ("PEM OpenSSH key header", "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----", "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----"),
    # A PGP header has BLOCK between KEY and the dashes, so a shape that ends at PRIVATE KEY----- misses it.
    ("PGP private key block header with a body line",
     "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----" + "\n" + PGP_BODY, "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----"),
    ("JWT", "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJ1c3IifQ" + "." + "c2lnbmF0dXJl",
     "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJ1c3IifQ" + "." + "c2lnbmF0dXJl"),
    ("Authorization Bearer header", "Authorization: Bearer " + "xq7Lp2Vw9Rt4Ys8Zn1Mh", "xq7Lp2Vw9Rt4Ys8Zn1Mh"),
    ("Authorization Basic header", "Authorization: Basic " + "dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("Cookie header", "Cookie: session=" + "abc123XYZ", "abc123XYZ"),
    ("Set-Cookie header", "Set-Cookie: sid=" + "q9W8e7R6t5Y", "q9W8e7R6t5Y"),
    ("session cookie in a value", "connect.sid=" + "s%3AabcDEF123.xyz456", "s%3AabcDEF123.xyz456"),
    ("URL access_token query value", "https://x/y?access_token=" + "abc123def456", "abc123def456"),
    ("URL key query value", "https://x/y?key=" + "AbC123dEf456", "AbC123dEf456"),
    ("URL sig query value", "https://x/y?sig=" + "Zq9Lm2Vw8Rt4", "Zq9Lm2Vw8Rt4"),
    ("password assignment", "password=" + "hunter2", "hunter2"),
    ("passwd assignment", "passwd=" + "hunter2", "hunter2"),
    ("pwd assignment", "pwd=" + "hunter2", "hunter2"),
    ("env-style password assignment", "DB_PASSWORD=" + "hunter2", "hunter2"),
    ("password with a colon", "password: " + "hunter2", "hunter2"),
    ("pwd with spaces around the sign", "pwd = " + "hunter2", "hunter2"),
    # A placeholder or a plain word is no secret only as the whole value. A secret after a placeholder, or a second
    # keyword after a shell path, is one.
    ("password with an angle-bracket value", "password: " + "<hunter2>", "hunter2"),
    ("password with a placeholder before a secret", "password: " + "<x>" + "hunter2", "hunter2"),
    ("password with a brace placeholder", "password: " + "${hunter2}", "hunter2"),
    ("password with a dollar name", "password: " + "$Tr0ub4dor", "Tr0ub4dor"),
    ("password with a percent name", "password: " + "%Hunter2%", "Hunter2"),
    ("PWD path with a second keyword after a semicolon", "PWD=/home/x;" + "password=" + "hunter2", "hunter2"),
    ("PWD path with a second keyword after an ampersand", "PWD=/home/x&" + "password=" + "hunter2", "hunter2"),
    # Refused today, kept so that a fix which matches a prefix, or a lower-case path, goes red.
    ("password with a plain word and digits", "password: " + "none123", "none123"),
    # A real password value stays refused when prose follows it on its line, and when it sits in backticks.
    ("password with a colon and a value of letters and digits", "password: " + "hunter2xyz", "hunter2xyz"),
    ("password with a real value before prose", "password: " + "hunter2xyz" + " for the guest.", "hunter2xyz"),
    ("password assignment in backticks", "`password=" + "hunter2xyz" + "`", "hunter2xyz"),
    ("lower-case pwd with a path value", "pwd=" + "/Users/x", "/Users/x"),
    ("email address", "person.name" + "@" + "example.com", "person.name@example.com"),
    ("phone number", "+1 (555) 010-2345", "+1 (555) 010-2345"),
    ("phone number with dots", "555" + "." + "010" + "." + "2345", "555.010.2345"),
    ("phone number with a country code and groups", "+44 20 7946 0958", "+44 20 7946 0958"),
    ("phone number in 3-3-4 with hyphens", "555-010-2345", "555-010-2345"),
    ("phone number in 3-3-4 with spaces", "555 010 2345", "555 010 2345"),
    ("phone as a JSON number", 5550102345, "5550102345"),
    ("token as a dict key", {"ghp_" + TAIL: "x"}, "ghp_" + TAIL),
    ("token nested in a list", ["fine", {"deep": "sk-ant-" + "aB3" * 12}], "sk-ant-" + "aB3" * 12),
    ("token after a comment opener", "see /* " + "ghp_" + TAIL, "ghp_" + TAIL),
    ("token after a lone quote", "Don't paste " + "ghp_" + TAIL, "ghp_" + TAIL),
    ("token in a multi-line string", "first line\nsecond line " + "ghp_" + TAIL + "\nthird line", "ghp_" + TAIL),
    ("street address", STREET, STREET),
    ("PO box", "PO BOX 1234", "PO BOX 1234"),
    ("P.O. box", "P.O. Box 1234", "P.O. Box 1234"),
    ("city, state and ZIP", "AUSTIN, TX 78701", "AUSTIN, TX 78701"),
    ("city, state and ZIP+4", "Austin, TX 78701-1234", "Austin, TX 78701-1234"),
    ("street address in a full line", "Send it to " + STREET + ", Austin, TX 78701", STREET),
    ("API_SECRET assignment", "API_SECRET=" + API_VALUE, API_VALUE),
    ("SESSION_TOKEN assignment", "SESSION_TOKEN=" + SESSION_VALUE, SESSION_VALUE),
    ("CLIENT_SECRET assignment with a colon", "CLIENT_SECRET: " + CLIENT_VALUE, CLIENT_VALUE),
    ("cf_clearance cookie value", "cf_clearance=" + "c3c3c3c3" + "c3c3c3c3", "c3c3c3c3" + "c3c3c3c3"),
    ("sessionid cookie value", "sessionid=" + "abcdef0123" + "456789abcd", "abcdef0123" + "456789abcd"),
    ("SESSION_COOKIE assignment", "SESSION_COOKIE=" + "abcdefgh" + "12345678", "abcdefgh" + "12345678"),
    ("bare Bearer token with no header name", "Bearer " + "abcdefghijkl" + "mnopqrstuvwx", "abcdefghijkl" + "mnopqrstuvwx"),
    ("TCG_TRACKING_KEY assignment", "TCG_TRACKING_KEY=" + "k9Qx7vLm" + "2Npw4Rt8", "k9Qx7vLm" + "2Npw4Rt8"),
    ("X-API-Key header", "X-API-Key: " + "abcdef" + "1234567890", "abcdef" + "1234567890"),
    ("secret: value", "secret: " + "abcd1234" + "efgh", "abcd1234" + "efgh"),
    ("token: value", "token: " + "abcd1234" + "efgh", "abcd1234" + "efgh"),
    ("bare Basic credential", "Basic " + "abcdefghij" + "klmnopqrst", "abcdefghij" + "klmnopqrst"),
    ("csrftoken cookie value", "csrftoken=" + "a1b2c3d4" + "e5f6g7h8", "a1b2c3d4" + "e5f6g7h8"),
    ("sid cookie value", "sid=" + "a1b2c3d4" + "e5f6g7h8", "a1b2c3d4" + "e5f6g7h8"),
    ("apiKey camelCase name", "apiKey: " + "abcd1234" + "efgh5678", "abcd1234" + "efgh5678"),
    ("clientSecret camelCase name", "clientSecret: " + CLIENT_VALUE, CLIENT_VALUE),
    ("apikey with no separator", "apikey=" + API_VALUE, API_VALUE),
    ("authtoken with a colon", "authtoken: " + SESSION_VALUE, SESSION_VALUE),
    ("SECRET_KEY_BASE assignment", "SECRET_KEY_BASE=" + "w8Kd2Lp9" + "Vx4Qz7Mn", "w8Kd2Lp9" + "Vx4Qz7Mn"),
    # A key word at the start of a name, after `_` or at a camelCase hump, still names a credential when its value has digits.
    ("secret_key assignment with digits", "secret_key=" + "Yt6Nb3Kd" + "Hj9Pq2Wr", "Yt6Nb3Kd" + "Hj9Pq2Wr"),
    ("GITHUB_TOKEN assignment with digits", "GITHUB_TOKEN=" + "Rt4Vb8Nm" + "Ls2Qw6Yp", "Rt4Vb8Nm" + "Ls2Qw6Yp"),
    # A key word glued to the word before it, with no `_` and no camelCase hump, still names a credential.
    ("CI_NPMTOKEN with an npm token value", "CI_NPMTOKEN=" + NPM_VALUE, NPM_VALUE),
    ("DEPLOY_GITHUBTOKEN with digits", "DEPLOY_GITHUBTOKEN=" + GLUED_VALUE, GLUED_VALUE),
    ("MYAPPSECRET with digits", "MYAPPSECRET=" + GLUED_VALUE, GLUED_VALUE),
    ("NPMTOKEN with digits", "NPMTOKEN=" + GLUED_VALUE, GLUED_VALUE),
    ("dbkey with digits", "dbkey=" + GLUED_VALUE, GLUED_VALUE),
    # A long name that ends in a key word is a credential name however long it runs before the word.
    ("a long name ending in token with digits",
     "token_for_the_production_environment_of_the_billing_service=" + GLUED_VALUE, GLUED_VALUE),
    ("API_KEY_V2 assignment", "API_KEY_V2=" + "Hk3Lm9Qp" + "Wz7Rt2Yc", "Hk3Lm9Qp" + "Wz7Rt2Yc"),
    ("clientSecret as a JSON pair", '"clientSecret": "' + CLIENT_VALUE + '"', CLIENT_VALUE),
    # A credential name set to a value of 12 or more characters is refused, digits or not. These values have no digit.
    ("API_KEY assignment of 12 letters", "API_KEY=" + LETTERS_12, LETTERS_12),
    ("GITHUB_TOKEN assignment of 16 letters", "GITHUB_TOKEN=" + LETTERS_16, LETTERS_16),
    ("CLIENT_SECRET with a colon and 16 letters", "CLIENT_SECRET: " + CLIENT_LETTERS_16, CLIENT_LETTERS_16),
    ("lower-case api_key in quotes of 14 letters", 'api_key = "' + LETTERS_14 + '"', LETTERS_14),
    # Raw JSON text: the closing quote of the name sits before the separator, so the name is not followed by = or :.
    ("raw JSON api_key pair of 16 letters", '"api_key": "' + LETTERS_16 + '"', LETTERS_16),
    ("raw JSON GITHUB_TOKEN pair of 16 letters", '"GITHUB_TOKEN": "' + LETTERS_16 + '"', LETTERS_16),
    # The letters-only branch of the credential-name shape, at the ends of its value: a comma, a newline, a semicolon, a
    # hump after two letters. Each value has no digit, so the digit branch does not refuse it.
    ("raw JSON api_key pair followed by a comma and a number", '{"api_key": "' + LETTERS_16 + '", "n": 1}', LETTERS_16),
    ("API_KEY of 12 letters before a newline", "API_KEY=" + LETTERS_12 + "\nOTHER=1", LETTERS_12),
    ("API_KEY of 12 letters before a CRLF", "API_KEY=" + LETTERS_12 + "\r\nOTHER=1", LETTERS_12),
    ("api_key in quotes followed by a semicolon", 'api_key = "' + LETTERS_14 + '";', LETTERS_14),
    ("api_key with a hump after only two lower-case letters", "api_key: " + HUMP_AFTER_TWO_16, HUMP_AFTER_TWO_16),
    # Random letters after the same names and separators as the GREEN placeholder and label values stay refused. A rule
    # keyed on the name, the separator, the case or an underscore would open these.
    ("Key with 16 random letters", "Key: " + LETTERS_16, LETTERS_16),
    ("api_key with 16 random capitals", "api_key: " + CAPS_16, CAPS_16),
    ("api_key with 16 random letters and an underscore", "api_key: " + UNDERSCORE_16, UNDERSCORE_16),
    ("--key-color with 16 random letters before a semicolon", "--key-color: " + LETTERS_16 + ";", LETTERS_16),
    # A letters-only value after a credential name is refused unless it reads as words, and only a `:` reaches that test:
    # an `=` is refused whatever the value. So the SECRET_KEY row, with `=`, pins no words step. The vowel row fails only
    # the vowel share, and the run row fails only the run check. Deleting the vowel share lets the vowel row through;
    # deleting the run check lets the run row through.
    ("SECRET_KEY set with = to letters that read as words", "SECRET_KEY=" + SUPER_PASSWORD, SUPER_PASSWORD),
    ("api_key of sixteen capitals with four vowels", "api_key: " + FEW_VOWELS_16, FEW_VOWELS_16),
    ("API_KEY of sixteen capitals with an eleven-consonant run", "API_KEY: " + LONG_CONSONANT_RUN_16, LONG_CONSONANT_RUN_16),
    ("api_key set to twelve underscores and no letter", "api_key: " + "_" * 12, "_" * 12),
    # A `:` value of letters passes only when every words check passes. The mixed-case row fails the word form alone, and
    # the vowel row fails the vowel share alone, so removing that check lets its row through. The run row fails the consonant
    # run alone: each of its parts holds a vowel. The lower-case row is refused by its run and by the vowel rule, so
    # removing one check does not let it through. The upper-case row has no vowel, and the share and the joined run refuse
    # it. The `=` row is refused whatever its value.
    ("a key name set with = to a hyphenated word", "key = '" + TIGHT_COMPACT + "'", TIGHT_COMPACT),
    ("secret of mixed-case words joined by a hyphen", "secret: '" + MIXED_HYPHEN + "'", MIXED_HYPHEN),
    ("secret of thirteen letters with three vowels", "secret: '" + SHORT_VOWELS + "'", SHORT_VOWELS),
    ("secret of a consonant run inside one word", "secret: '" + RUN_PART + "'", RUN_PART),
    ("secret of lower-case letters with no vowel", "secret: '" + CONSONANT_HYPHEN + "'", CONSONANT_HYPHEN),
    ("secret of upper-case three-letter parts joined by hyphens", "secret: '" + UPPER_HYPHEN + "'", UPPER_HYPHEN),
    ("secret of five consonants in one hyphen part", "secret: '" + RUN5_HYPHEN + "'", RUN5_HYPHEN),
    ("secret of five consonants in one part joined by an underscore", "secret: '" + RUN5_UNDERSCORE + "'", RUN5_UNDERSCORE),
    ("secret of lower-case letters with few vowels and no separator", "secret: '" + FEW_VOWEL_WORD + "'", FEW_VOWEL_WORD),
    ("secret of all-lower snake_case parts with no vowel", "secret: '" + VOWELLESS_SNAKE + "'", VOWELLESS_SNAKE),
    ("secret of all-lower hyphen parts with no vowel", "secret: '" + VOWELLESS_HYPHEN + "'", VOWELLESS_HYPHEN),
    ("street with the suffix Park", "1400 Lakeshore Park", "1400 Lakeshore Park"),
    ("street with the suffix Trail", "2500 Maple Trail", "2500 Maple Trail"),
    ("street with the suffix Cir", "1200 Oak Cir", "1200 Oak Cir"),
    ("street with the suffix Ter", "400 Pine Ter", "400 Pine Ter"),
    # Over-widening guard: a placeholder or a tool value must not open these real-looking values.
    ("password with a real-looking value", "password: " + "S3cr3t!x9", "S3cr3t!x9"),
    ("pwd assignment with a real-looking value", "pwd=" + "hunter2x", "hunter2x"),
    ("personal address with a dotted name", "jane.doe" + "@" + "example.com", "jane.doe@example.com"),
    ("personal address on a personal host", "jane" + "@" + "myhost.example.com", "jane@myhost.example.com"),
    ("personal ssh-form remote on a personal host", "jane" + "@" + "myhost.example.com:notes.git",
     "jane@myhost.example.com:notes.git"),
    # A mask is no secret only as the whole value. A no-reply name is no person only as the whole local part, and an
    # ssh remote of a public git host is no person only when its local part is `git`.
    ("password with asterisks before a secret", "password: " + "***" + "hunter2", "hunter2"),
    ("personal name in the ssh form of a public git host", "jane" + "@" + "github.com:x", "jane@github.com:x"),
    ("no-reply name before a personal name", "noreply-jane" + "@" + "x.com", "noreply-jane@x.com"),
    ("no-reply name after a personal name", "jane.noreply" + "@" + "x.com", "jane.noreply@x.com"),
    # A plain word is no secret only as the whole value. A secret after one, with or without a comma or quotes, is one.
    ("password with a plain word before a secret", "password: " + "none hunter2", "hunter2"),
    ("password with a plain word and a comma before a secret", "password: " + "none, hunter2", "hunter2"),
    ("password with a quoted plain word before a secret", "password: " + '"none" hunter2', "hunter2"),
    # Real-looking secrets of the three kinds whose false positives are narrowed: they stay refused.
    ("credential name with a live-key value", "API_KEY='" + "sk_live_" + "9fQ2xZ7Lk3'", "9fQ2xZ7Lk3"),
    ("password in minified code with a real value", 'password:"' + "hunter2" + '-Secret!"', "hunter2-Secret!"),
    ("URL credentials on a host name with a short password", "https://user:" + "p4ss" + "@host.example.com/", "p4ss"),
    ("password that starts with !0", "password:" + "!0hunter2", "!0hunter2"),
    ("credential name with a value that starts with return", "api_key=" + "return9fQ2xZ7Lk3", "return9fQ2xZ7Lk3"),
    # A URL password may hold a bracket, a bar or a quote: the credential is still in the URL. Each password is joined from parts.
    ("URL password with a bar", "https://user:" + "pa|ss" + "@host", "pa|ss"),
    ("URL password with brackets", "postgres://app:" + "Qz9(Lk2Xm7)" + "@db.internal/x", "Qz9(Lk2Xm7)"),
    ("URL password with quotes around it", 'https://user:"' + "secret1" + '"@api.example.com/', "secret1"),
    ("URL password with dollars and brackets on an IP host", "mongodb://admin:" + "Pa$$(word)" + "@10.0.0.7:27017",
     "Pa$$(word)"),
    # A minified boolean such as !0 or !1 after a password word is not the value: the real value after it is the secret.
    ("password with a minified boolean and a comma before a real value", "password:" + "!0," + "hunter2", "hunter2"),
    ("password with = and a minified boolean before a real value", "password=" + "!0," + "Xk9mP2qL", "Xk9mP2qL"),
    ("password with a minified boolean and a semicolon before a real value", "password: " + "!1;" + "Tr0ub4dorX",
     "Tr0ub4dorX"),
    ("password with a minified boolean and a space before a real value", "password: " + "!0 " + "hunter2secret",
     "hunter2secret"),
    # A credential name, a keyword prefix, a symbol, then a real value: the value after the symbol is the secret.
    ("api_key with a keyword prefix, a hyphen and a real value", "api_key=" + "return-" + "9fQ2xZ7Lk3",
     "return-9fQ2xZ7Lk3"),
    ("token with a keyword prefix, a plus and a real value", "token=" + "void+" + "Ab3dEf7Hi9", "void+Ab3dEf7Hi9"),
    ("SECRET with a keyword prefix, a tilde and a real value", "SECRET=" + "typeof~" + "Kq8LmZ2xW", "typeof~Kq8LmZ2xW"),
    # A URL password may hold a closing paren, a quote, a brace or a pair of bars, and an IPv6 host is in brackets: the
    # credential is still in the URL, so each row refuses.
    ("URL password with a closing paren on a host name", "postgres://app:" + "Qz9Lk2Xm7)" + "@localhost:5432/db", "Qz9Lk2Xm7)"),
    ("URL password with a quote inside it", "postgres://app:" + "O'Neil2020" + "@localhost/db", "O'Neil2020"),
    ("URL password with a brace on a MySQL host with a port", "mysql://root:" + "pa}ss" + "@db:3306/app", "pa}ss"),
    ("URL password on a bracketed IPv6 host", "postgres://app:" + "Qz9Lk2Xm7" + "@[::1]:5432/db", "Qz9Lk2Xm7"),
    ("URL password with two bars and a bare host", "https://u:" + "p||" + "@h", "p||"),
    # A minified boolean is no value, and a member after it can hold one: each member after the boolean is checked alone.
    ("password word, a boolean, then pwd with a real value", "password:" + "!0," + "pwd:" + "hunter2", "hunter2"),
    ("password word, a boolean, then password with a real value", "password:" + "!0," + "password:" + "hunter2", "hunter2"),
    ("password word, a boolean, then token with a real value", "password:" + "!0," + "token:" + "hunter2", "hunter2"),
    ("password word, a boolean, then pass with a real value", "password:" + "!0," + "pass:" + "Tr0ub4dor", "Tr0ub4dor"),
    ("password word, a boolean, then a semicolon assignment", "password:" + "!0;" + "a=" + "hunter2", "hunter2"),
    ("password word, a boolean, then a brace and a pwd assignment", "password:" + "!0};" + "pwd=" + "hunter2", "hunter2"),
    # Hole 1: a connection string built by concatenation. The password before the `@` is a literal, and the host after
    # the `@` is code, so the literal is still a credential in the URL.
    ("concatenated postgres DSN with a literal password and a code host",
     'dsn = "postgres://admin:' + SUP_PASSWORD + '@" + host + "/app"', SUP_PASSWORD),
    ("concatenated mongodb URL with a literal password and a code host",
     "'mongodb://admin:" + SUP_PASSWORD + "@' + HOST", SUP_PASSWORD),
    ("concatenated mysql URL with a literal password and an environ host",
     '"mysql://root:' + PASSWORD + '@" + os.environ["DB_HOST"]', PASSWORD),
    # Hole 2: a literal password before a template or shell host. The host is a placeholder, so the password is a secret.
    ("postgres URL with a literal password and a braced template host",
     "postgres://admin:" + SUP_PASSWORD + "@{db_host}/app", SUP_PASSWORD),
    ("postgres URL with a literal password and a double-braced template host",
     "postgres://admin:" + SUP_PASSWORD + "@{{ db_host }}/app", SUP_PASSWORD),
    ("postgres URL with a literal password and a braced host with a port",
     "postgres://admin:" + SUP_PASSWORD + "@{host}:5432", SUP_PASSWORD),
    ("postgres URL with a literal password and an angle-bracket host",
     "postgres://admin:" + SUP_PASSWORD + "@<host>/app", SUP_PASSWORD),
    ("postgres URL with a literal password and a bare shell host",
     "postgres://admin:" + SUP_PASSWORD + "@$HOST/app", SUP_PASSWORD),
    ("postgres URL with a literal password and a braced shell host",
     "postgres://admin:" + SUP_PASSWORD + "@${HOST}/app", SUP_PASSWORD),
    # A literal password may hold a code character, one of + | ( ) [ ] { }, and the host after its @ may be code, a quote,
    # a brace or a bracket. The password is still a literal before the @, so the URL carries a credential.
    ("concatenated DSN with a plus in the literal password, then @ and a quote",
     'dsn = "postgres://admin:' + "Pa+ss" + '@" + host', "Pa+ss"),
    ("postgres URL with a plus in the literal password and a braced template host",
     "postgres://admin:" + "Pa+ss" + "@{db_host}/app", "Pa+ss"),
    ("https URL with two bars in the literal password, then @ and a quote",
     "https://u:" + "p||" + '@"+h', "p||"),
    ("https URL with two bars in the literal password and a braced host",
     "https://u:" + "p||" + "@{h}", "p||"),
    ("postgres URL with parens in the literal password and a braced host",
     "postgres://admin:" + "p(w)" + "@{host}/app", "p(w)"),
    # A templated or shell user does not make the password a placeholder. The literal after the user's colon is the credential,
    # whatever the host is: a dotless host, a templated host or a braced one.
    ("postgres URL with a templated user, a literal password and a dotless host",
     "postgres://{user}:" + SUP_PASSWORD + "@localhost:5432/app", SUP_PASSWORD),
    ("f-string postgres URL with a templated user, a literal password and a templated host",
     'f"postgres://{user}:' + SUP_PASSWORD + '@{host}/app"', SUP_PASSWORD),
    ("postgres URL with a shell-variable user, a literal password and a braced template host",
     "postgres://${USER}:" + SUP_PASSWORD + "@{db_host}/app", SUP_PASSWORD),
    # A templated user that is not a whole {word} does not make the password a placeholder. The literal after the user's
    # colon is the credential, whatever the template form and whatever the dotted host. Today the email rule refuses these
    # rows, since Hunter2xx@db.example.com reads as an address; the family after the postgres rows is the one that pins
    # the URL-credentials rule.
    ("postgres URL with an attribute user, a literal password and a dotted host",
     "postgres://{cfg.user}:" + HUNTER_PASSWORD + "@db.example.com/app", HUNTER_PASSWORD),
    ("postgres URL with a self attribute user, a literal password and a dotted host",
     "postgres://{self.user}:" + HUNTER_PASSWORD + "@db.example.com/app", HUNTER_PASSWORD),
    ("postgres URL with a double-braced user, a literal password and a dotted host",
     "postgres://{{user}}:" + HUNTER_PASSWORD + "@db.example.com/app", HUNTER_PASSWORD),
    ("postgres URL with a percent-format user, a literal password and a dotted host",
     "postgres://%(user)s:" + HUNTER_PASSWORD + "@db.example.com/app", HUNTER_PASSWORD),
    ("postgres URL with a dotted shell-variable user, a literal password and a dotted host",
     "postgres://${var.db_user}:" + HUNTER_PASSWORD + "@db.example.com/app", HUNTER_PASSWORD),
    ("postgres URL with a conversion-flag user, a literal password and a dotted host",
     "postgres://{user!r}:" + HUNTER_PASSWORD + "@db.example.com/app", HUNTER_PASSWORD),
    ("postgres URL with an indexed user, a literal password and a dotted host",
     "postgres://{cfg[user]}:" + HUNTER_PASSWORD + "@db.example.com/app", HUNTER_PASSWORD),
    # A literal password may hold a quote. The quote sits in the password, so a quote or a brace after the @ is still a host.
    ("postgres URL with a quote in the literal password, then @ and a quote and a plus",
     "postgres://admin:" + QUOTE_PASSWORD + '@"+h', QUOTE_PASSWORD),
    ("f-string URL with a double quote in the literal password and a braced template host",
     'f"postgres://admin:' + QUOTE_IN_PASSWORD + '@{host}/db"', QUOTE_IN_PASSWORD),
    # A key word inside a longer name is a credential name too. The stem of an everyday word (mon, turn, hoc) is no
    # reason to skip it. The value is the one the turnkey control in GREEN uses.
    ("commonKey with a value of letters and digits", "commonKey: " + GLUED_VALUE, GLUED_VALUE),
    ("daemonKey with a value of letters and digits", "daemonKey: " + GLUED_VALUE, GLUED_VALUE),
    ("adHocKey with a value of letters and digits", "adHocKey: " + GLUED_VALUE, GLUED_VALUE),
    ("returnKey with a value of letters and digits", "returnKey: " + GLUED_VALUE, GLUED_VALUE),
    # A letters-only secret after a plain word and prose is one. The prose after the plain word must not hide it.
    ("letters-only secret after a plain word, a semicolon and `is`",
     "password: required to log in; default is swordfish", "swordfish"),
    ("letters-only secret after a plain word and `and`", "password: none and swordfish", "swordfish"),
    # Each separator word or mark before a non-function word starts a second value, so the password value is refused.
    ("letters-only secret after a plain word and `or`", "password: none or swordfish", "swordfish"),
    ("letters-only secret after a plain word and `but`", "password: none but swordfish", "swordfish"),
    ("letters-only secret after a plain word and `is`", "password: none is swordfish", "swordfish"),
    ("letters-only secret after a plain word and `are`", "password: none are swordfish", "swordfish"),
    ("letters-only secret right after a plain word and a semicolon", "password: none; swordfish", "swordfish"),
    ("one-word letters-only secret after a plain word, prose and a comma","password: none for the guest, swordfish", "swordfish"),
    # A comma does not end the prose: a letters-only secret after a comma, with prose before it, is one.
    ("25-letter letters-only passphrase after a plain word, prose and a comma","password: none for the admin account, " + PROSE_SECRET, PROSE_SECRET),
    # The digit counts wherever it sits in the value: at 256, and at 257 and 1000 past it.
    ("digit at index 256 of a credential value", "API_KEY=" + CAP_LAST_DIGIT, CAP_LAST_DIGIT),
    ("digit at index 257 of a credential value", "API_KEY=" + DIGIT_AT_257, DIGIT_AT_257),
    ("digit at index 1000 of a credential value", "API_KEY=" + DIGIT_AT_1000, DIGIT_AT_1000),
    # The letter at index 300 is past the short shape's window, so only the long-value shape can see it. It refuses.
    ("API_KEY of 300 digits then a letter", "API_KEY=" + DIGITS_300_THEN_LETTER, DIGITS_300_THEN_LETTER),
    # A semicolon after prose starts a second value as a comma does. Only the `;` in the separator check refuses this.
    ("letters-only secret after prose and a semicolon", "password: none for the guest; swordfish", "swordfish"),
    # A prose tail after a plain value passes only as a function word first, then letter words. A letter word with no
    # function word first, a digit in a later word, and a symbol inside a later word each refuse.
    ("password none then a letter word with no function word first", "password: none " + "swordfish", "swordfish"),
    ("password none then a function word and a word with a digit", "password: none for " + "hunter2", "hunter2"),
    ("password none then a function word and a word with a trailing mark and a digit",
     "password: none for " + "hunter2!", "hunter2!"),
    ("password none then a function word and a symbol inside a word", "password: none for " + "hunter&co", "hunter&co"),
    # VALUE_LOOKAHEAD_MAX pin: a value whose digit sits past the first 20 characters is refused only at the full cap.
    ("api_key of 200 letters, one 16-letter block repeated, then a digit", "api_key: " + LETTERS_200 + "7", LETTERS_200 + "7"),
    # Control for the pin above: the same 200 letters with no digit are refused by the letters-only branch at any cap.
    ("api_key of 200 letters, one 16-letter block repeated, with no digit", "api_key: " + LETTERS_200, LETTERS_200),
]
# A paren in the password keeps the email rule from reading the dotted host as an address, so only the URL-credentials rule
# can refuse these. Each templated user form must refuse on its own.
TEMPLATED_USERS = ("{cfg.user}", "{self.user}", "{{user}}", "%(user)s", "${var.db_user}", "{user!r}", "{cfg[user]}")
RED += [("templated user %s, a literal password with a paren and a dotted host" % user,
         "postgres://" + user + ":" + HUNTER_PASSWORD + "(@db.example.com/app", HUNTER_PASSWORD + "(")
        for user in TEMPLATED_USERS]
# Dashed and short vendor-style keys, each set in four credential-name carriers. Each value is joined from parts, so no
# key-looking literal sits whole in the source. A hyphen-joined value of letters and digits is a key shape, so the
# hyphen-words rule must not pass it. The underscored row and the six-character last part are refused today; they pin
# that a fix keeps the refusal.
DASHED_KEYS = (
    ("dashed sk live key", "sk-" + "live-" + "ab12"),
    ("underscored sk live key", "sk_" + "live_" + "ab12"),
    ("dashed sk test key", "sk-" + "test-" + "ab12"),
    ("dashed pk live key", "pk-" + "live-" + "ab12"),
    ("dashed sk live key with a six-character last part", "sk-" + "live-" + "ab12cd"),
    ("dashed ghp token", "ghp-" + "ab12cd"),
    ("dashed rk live key", "rk-" + "live-" + "ab12"),
)
KEY_CARRIERS = (
    ("KEY single-quoted", "KEY='%s'"),
    ("api_key unquoted", "api_key=%s"),
    ("token with a colon", "token: %s"),
    ("SECRET_KEY double-quoted", 'SECRET_KEY="%s"'),
)
RED += [("%s in %s" % (name, carrier), fmt % value, value)
        for name, value in DASHED_KEYS for carrier, fmt in KEY_CARRIERS]
# Dashed vendor-style keys after an unquoted KEY= or token= carrier. A separate tuple: KEY_CARRIERS also feeds the 7-character GREEN rows.
VENDOR_KEYS = (
    ("dashed sk proj key", "sk-" + "proj-" + "abcdefgh1"),
    ("dashed sk ant key", "sk-" + "ant-" + "api03-" + "abcdefg1"),
    ("dashed stripe live key", "stripe-" + "live-" + "ab12"),
    ("dashed sk proj live key", "sk-" + "proj-" + "live-" + "ab12"),
    ("dashed sk key of nine characters", "sk-" + "abcd12"),
    ("dashed ghp key of eight characters", "ghp-" + "ab12"),
)
VENDOR_CARRIERS = (("KEY unquoted", "KEY=%s"), ("token unquoted", "token=%s"))
RED += [("%s in %s" % (name, carrier), fmt % value, value)
        for name, value in VENDOR_KEYS for carrier, fmt in VENDOR_CARRIERS]

# (label, the note's value). Words, a URL, a time, an id and a number that are not secrets pass.
GREEN = [
    ("token budget", "token budget"),
    # Code text the scan misread: a localStorage key name, a minified JS boolean, a URL-looking run that crosses quotes,
    # brackets and `|`, and keyCode handling.
    ("key name of lower-case words joined by hyphens", "KEY='automations-v3-review'"),
    # Hyphen-joined lower-case words with a digit take the hyphen-words path, the path a fix to the key shape narrows. Each
    # has a short part (`key`, `v`), so a fix that refuses short parts goes red here.
    ("key name of hyphen words with a short part and a digit", "KEY='cache-key-v2'"),
    ("token name of hyphen words with a short part and a digit", "token: page-length-v2"),
    ("storage key name of hyphen words with a short part and a digit", 'storageKey:"page-length-v2"'),
    # A keyword word, then a space and a digit, is minified code. It is not a secret, and a keyword-prefix fix must not refuse it.
    ("minified void 0 after a token word", "token:void 0,"),
    ("minified JS boolean after a password word", "password:!0"),
    ("minified code with :// and a colon and @ across quotes and brackets", '"https://a"})];U&&(c=I==null||x:y@b'),
    # A password made of code, a quote and `+`, then `@` and a quote, is code and not a credential. It must stay green
    # once the hole rows above refuse a literal password before the `@`.
    ("code password joined by plus, then @ and a quote", '"http://h:"+port+"@"'),
    ("code password joined by plus, then @[ and code", '"http://h:"+p+"@["+x'),
    ("minified keyCode comparison", "e.keyCode===13&&e.preventDefault()"),
    # The same shapes as a real bundled page has them: booleans in a run, and a switch case on a key event name.
    ("minified JS booleans in a run after a password word", "password:!0,range:!0,search:!0,tel:!0};function"),
    ("minified switch case on a key event name", 'switch(a){case "keyup":return-1!==Hj.indexOf(b.keyCode);'),
    ("password manager", "password manager"),
    ("private key rotation", "rotate the private key"),
    # A public key block is not a secret. A fix that drops PRIVATE from the shape would refuse it.
    ("PGP public key block header with a body line", "-----BEGIN " + "PGP PUBLIC KEY BLOCK-----" + "\n" + PGP_BODY),
    ("owner's first name", "Shivam"),
    ("comment openers and a lone quote", "Don't use /* or // or # here"),
    ("multi-line text", "line one\nline two"),
    ("artifact link", ARTIFACT),
    ("ISO time", "2026-11-02T11:04:00Z"),
    ("date", "2026-11-02"),
    ("date and time in the space form", "2026-11-02 11:04"),
    ("a risk- word with no space", "risk-based-approval-of-the-change"),
    ("a CSS class with sk- in it", "btn-sk-primary-large-rounded"),
    ("an SVG viewBox and points of single digits", '<svg viewBox="0 0 24 24"><polyline points="1 2 3 4 5 6 7 8 9 0 1 2"/></svg>'),
    ("SVG points of three digits", 'points="100 200 300 400"'),
    ("an ICR number with dashes", "ICR 2026-0412-0031"),
    ("a PO number of ten digits", "PO 4500123456"),
    ("an IPv4 address", "192.168.100.200"),
    ("a messageId of thirteen digits", "messageId=1730000000000"),
    ("a messageId as a JSON number", {"messageId": 1730000000000}),
    ("u_ id of 22 characters", "u_Qm4xT7bR2nKs9LfW0aZc"),
    ("u_ id of 24 characters", "u_Qm4xT7bR2nKs9LfW0aZcYe"),
    ("a key named token", {"token": "budget"}),
    ("a number with 14 digits, not a string", {"n": 20261102110400, "note": "budget"}),
    # Near misses of the address and credential shapes: a street word, a state code before a five-digit number, a rule name.
    ("step number of three digits", "step 123"),
    ("a street name with no number", "Main Street"),
    ("PR number before the word lane", "PR 1167 batch lane"),
    ("a digit before the word road", "step 3 on the road map"),
    ("a digit before the word way", "a 2 way merge"),
    ("a digit before a hyphenated word", "lane 4 drive-by fix"),
    ("PR with a five-digit number", "merged, PR 12345"),
    ("OK with a five-digit number", "done, OK 12345"),
    ("a bare rule name in caps with TOKEN", "TOKEN_BUDGET"),
    ("a TOKENS setting with a number", "CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000"),
    ("a MAX_TOKENS setting with a number", "MAX_TOKENS=200000"),
    ("a model setting", "CLAUDE_CODE_SUBAGENT_MODEL=sonnet"),
    ("a CI secret reference", "GITHUB_TOKEN=${{ secrets.GITHUB_TOKEN }}"),
    ("an env-var reference in a secret name", "API_SECRET=$API_SECRET"),
    ("a rule anchor name", "rule roles-review-cap-three"),
    ("a count of records", "3 records in place"),
    ("a count of cards", "5 cards in this lane"),
    ("a join key label with a colon", "join key:"),
    ("a JSX key prop", "key={item.id}"),
    ("a token label with a plain word", "token: budget"),
    ("a secret label with no value", "secret: none"),
    ("the word Basic in prose", "Basic idea: keep it short"),
    ("the word sid in prose", "sid is the session id"),
    ("a token budget label with a number", "token budget: 200000"),
    ("a KEY label with prose", "KEY: see the record"),
    # Prose with a time or a number before a street word or a key word is no address and no credential name, so it passes.
    ("a time and a street word in prose", "Meeting 13:44 CDT. Lane 2 is open"),
    ("a time with PM and a street word in prose", "Due 5 PM. Way forward is clear"),
    ("a number before the word Park in prose", "Phase 2 Park the lane"),
    ("a key inside a longer word", "turnkey solution"),
    # A key word inside a longer word is no credential name, even with a value of letters and digits after it.
    ("a key word inside a longer word with a value", "monkey: Banana12345"),
    ("a key word inside a longer word with a camel value", "hotkey: Ctrl1Shift2"),
    # The control for the longer names in RED: the everyday word with the same value passes.
    ("turnkey with a value of letters and digits", "turnkey: " + GLUED_VALUE),
    # The same holds for other words that end in key, with a value of letters and digits.
    ("turkey with a value", "turkey: Gobble2024"),
    ("donkey with a value", "donkey: Kong1981"),
    ("whiskey with a value", "whiskey: Jameson12"),
    ("jockey with a value", "jockey: Rider123"),
    # Each word of EVERYDAY_KEY_WORDS has its own row with a random-looking value. Dropping a word from the list
    # turns that row red.
    ("turnkey with a random value", "turnkey=" + "Xq7Zt2Lm" + "9Qw4"),
    ("hockey with a random value", "hockey: " + "Rk4Ps8Vn" + "2Tz6"),
    ("lackey with a random value", "lackey=" + "Wm3Bq9Jd" + "5Hx7"),
    ("a keyboard label with a number", "keyboard: 104 keys"),
    # A shell variable, an ssh remote, a no-reply address, and the placeholders and masks: none names a secret.
    ("password word with optional", "password: " + "optional"),
    ("shell working-dir variable", "PWD" + "=" + "/Users/x"),
    ("ssh remote of a public host", "git" + "@" + "github.com:" + "owner/repo.git"),
    ("no-reply address", "noreply" + "@" + "anthropic.com"),
    ("password placeholder none", "password: " + "none"),
    ("password mask", "password: " + "*" * 8),
    ("password template placeholder", "Password: " + "<your-password>"),
    ("env var from a template", "POSTGRES_" + "PASSWORD=" + "${DB_PASSWORD}"),
    # A placeholder or a plain word inside quotes, brackets or parentheses, and a quoted shell path, name no secret.
    ("quoted optional after a password word", "password: " + '"optional"'),
    ("plain word in parentheses after a password word", "(password: none)"),
    ("bracketed optional after a password word", "password: " + "[optional]"),
    ("quoted shell path after PWD", 'PWD="/home/x"'),
    # A placeholder, a mask or a plain word after a password word is no secret when it is the whole value.
    ("password word with a shell variable", "password: " + "$DB_PASSWORD"),
    ("password word with a brace template", "password: " + "{{DB_PASSWORD}}"),
    ("password word with a percent template", "password: " + "%DB_PASSWORD%"),
    ("password word with xxx", "password: " + "xxx"),
    ("password word with a bullet mask", "password: " + "•" * 3),
    ("single-quoted optional after a password word", "password: " + "'optional'"),
    ("parenthesized none after a password word", "password: " + "(none)"),
    ("none with a period after a password word", "password: " + "none."),
    # A placeholder word with prose after it on the same line, and a backticked shell path, name no secret.
    ("password word with optional and prose after it", "Set password: optional for the guest."),
    ("password word with none and prose after it", "password: none for the guest"),
    # A function word after a comma is no second value: only a non-function word after a separator is one.
    ("password word with none, prose, a comma and a function word", "password: none for the guest, and the"),
    ("backticked shell path after PWD", "`PWD=/Users/x`"),
    # Near misses of the three new shapes: a digit count, a tail length, a prefix inside a word, and a clock time pass.
    ("Telegram token with 11 digits before the colon", "12345678901:" + TG_TAIL),
    ("Telegram token with a 34-character tail", "123456789:" + TG_TAIL[:34]),
    ("Telegram token with a 36-character tail", "123456789:" + TG_TAIL + "x"),
    ("a clock time", "standup at 10:30"),
    ("Docker Hub PAT with 19 characters", "dckr_pat_" + "aB3" * 6 + "a"),
    ("Stripe test key with 15 characters", "sk_test_" + "aB3" * 5),
    ("a word that holds the Stripe test prefix", "risk_test_coverage_plan"),
    ("a word that holds the Stripe test prefix before a long body", "risk_test_" + "aB3" * 7),
    # A credential name below 12 characters, a placeholder, a variable reference, a plain word and prose pass.
    ("API_KEY with 11 letters", "API_KEY=" + LETTERS_11),
    ("API_KEY set to a placeholder", "API_KEY=<your-api-key>"),
    ("API_KEY set to a long variable reference", "API_KEY=${MY_LONG_API_KEY_NAME}"),
    ("MY_TOKEN set to a plain word", "MY_TOKEN=optional"),
    ("MY_TOKEN set to a long placeholder", "MY_TOKEN=<your-long-token-here>"),
    # The RED value at 1000 with no credential name in front: a fix that refuses any long value with a digit fails here.
    ("a long run of letters with a digit at index 1000, and no credential name", DIGIT_AT_1000),
    # 300 digits and no letter is no secret: the long-value shape refuses only a value with a letter and a digit.
    ("API_KEY of 300 digits and no letter", "API_KEY=" + DIGITS_300),
    # 300 letters and no digit is no secret: the long-value shape refuses only a value with a letter and a digit. A fix that
    # refuses any letter in a long value turns this row red.
    ("token with 300 letters and more words", "token: " + LETTERS_300 + " and more words"),
    ("prose with the word secret before a name", "the secret santa list"),
    # A letters-only value of 12 or more characters after a credential name refuses today. These three are placeholder and
    # label text, not secrets, so each is red on main. The RED rows above hold a random value after the same names.
    ("api_key set to an upper-case placeholder with underscores", "api_key: REPLACE_WITH_YOUR_KEY"),
    ("Key set to a lower-case label word", "Key: infrastructure"),
    ("--key-color set to a CSS keyword before a semicolon", "--key-color: currentcolor;"),
    # A plain option key whose value is a hyphenated word is no secret, in a line of text or in a JS object line.
    ("option key icon-compact", "key: '" + ICON_COMPACT + "'"),
    ("option key tight-compact", "key: '" + TIGHT_COMPACT + "'"),
    ("option key tight-compact in a JS object line", "{ key: '" + TIGHT_COMPACT + "', label: 'Tight' }"),
    # A hyphen or underscore option key with a word of four consonants, and the snake_case form, is no secret.
    ("option key page-length-limit", "key: '" + PAGE_LENGTH_LIMIT + "'"),
    ("option key strength-meter", "key: '" + STRENGTH_METER + "'"),
    ("option key bright-lights-city", "key: '" + BRIGHT_LIGHTS_CITY + "'"),
    ("option key tight_compact in snake case", "key: '" + TIGHT_SNAKE + "'"),
    ("option key page_length_limit in snake case", "key: '" + PAGE_SNAKE + "'"),
    # A part of one to three letters is exempt from the vowel rule, so `db` and `btn` pass. A part of four or more letters
    # holds a vowel, and `y` is one, so `lynx` and `sync` pass on their `y`. The values run 12 characters or more, the length
    # the words check needs to reach them.
    ("option key db-connection-pool, with a two-letter part", "key: 'db-connection-pool'"),
    ("option key db_connection_pool in snake case, with a two-letter part", "key: 'db_connection_pool'"),
    ("option key btn-primary-hover, with a three-letter part", "key: 'btn-primary-hover'"),
    ("option key lynx_sync_mode, whose parts have y as their only vowel", "key: 'lynx_sync_mode'"),
    # `text-transform` is the green control beside the red rows: each part holds a vowel, and no part has five consonants in a
    # row, so it passes. `flex_shrink` is 11 characters, under the 12-character length, so it never reaches the words check and
    # pins nothing about the vowel rule.
    ("option key text-transform", "key: 'text-transform'"),
    ("option key flex_shrink", "key: 'flex_shrink'"),
    # The names that do not count under the rule (bare token, camelCase, a hyphenated or a non-credential name) pass.
    # These four are false alarms today: each refuses on its value's length, so they are red on the builder's head.
    ("destructured token alias", "const { token: accessTokenValue } = await getSession();"),
    ("camelCase accessToken key with a call", "accessToken: localStorage.getItem('accessToken')"),
    ("CSS custom property ending in token", "--color-token: rgba(0,0,0,0.5);"),
    ("prose with Token before a sentence", "Token: Authorization needed before we continue"),
]

# A 7-character value is under the shared 8-character floor on purpose, so each carrier passes.
SEVEN_CHAR_KEYS = (("dashed sk key of seven characters", "sk-" + "ab12"),)
GREEN += [("%s in %s" % (name, carrier), fmt % value)
          for name, value in SEVEN_CHAR_KEYS for carrier, fmt in KEY_CARRIERS]


def canonical(data):
    """The bytes a copy holds for `data`: sorted keys, two-space indent, a trailing newline."""
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def skill_file_with(heading):
    """The text of the skill file that holds the section which starts with the `heading` line: SKILL.md, or one of its
    reference/*.md files, where the skill moved its topics. Read from disk each time, never copied here."""
    for path in [os.path.join(HERE, "SKILL.md")] + sorted(glob.glob(os.path.join(HERE, "reference", "*.md"))):
        text = read_text(path)
        if heading in text:
            return text
    raise AssertionError("neither SKILL.md nor reference/*.md has a '%s' section" % heading)


def skill_step(heading, n):
    """The text of step `n` in the section that starts with the `heading` line, read from the skill file that holds it and
    never copied here. The step runs to the next step, or to the next section."""
    sections = skill_file_with(heading).split(heading, 1)
    steps = sections[1].split("\n## ", 1)[0].split("\n%d. " % n, 1)
    if len(steps) != 2:
        raise AssertionError("the '%s' section has no step %d" % (heading, n))
    return steps[1].split("\n%d. " % (n + 1), 1)[0]


def page_with(snippet):
    """The fixture page with `snippet` before its designData block, so the snippet's text sits outside the block."""
    return PAGE.replace(DESIGN_ELEMENT, snippet + DESIGN_ELEMENT, 1)


def page_snippets():
    """(label, snippet, secret): a secret-shaped value in page text outside designData, at each shape of text a scanner
    could misread: a comment opener inside a string, a multi-line template literal, a lone quote, and an email."""
    return (
        ("token in a paragraph", "<p>Token: %s</p>\n" % TOKEN, TOKEN),
        ("token after a comment opener in a CSS string", '<style>.x::before { content: "/* %s"; }</style>\n' % TOKEN, TOKEN),
        ("token after // in a JS string", '<script>const a = "// %s";</script>\n' % TOKEN, TOKEN),
        ("token in a multi-line template literal", "<script>\nconst t = `first line\nsecond line %s\nthird line`;\n</script>\n" % TOKEN,
         TOKEN),
        ("token after a lone quote in text", "<p>Don't paste %s</p>\n" % TOKEN, TOKEN),
        ("email address in text", "<p>Contact %s</p>\n" % MAIL, MAIL),
        ("URL credentials on an IP host with a port", "<p>Database: %s</p>\n" % DB_IP_URL, PASSWORD),
        ("URL credentials on an IP host with no port", "<p>Build: %s</p>\n" % BUILD_IP_URL, PASSWORD),
        ("URL credentials on a host name, the control", "<p>Database: %s</p>\n" % DB_NAME_URL, PASSWORD),
    )


def snapshot(folder):
    """Every file and folder under `folder` with its bytes, so a run that writes anything shows as a change."""
    found = {}
    if not os.path.isdir(folder):
        return found
    for dirpath, dirnames, names in os.walk(folder):
        for name in dirnames:
            found[os.path.relpath(os.path.join(dirpath, name), folder) + "/"] = None
        for name in names:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                found[os.path.relpath(path, folder)] = f.read()
    return found


def verdict_lines(r):
    """The stripped, non-empty lines the run printed on either stream."""
    return [line.strip() for line in (r.stdout + r.stderr).splitlines() if line.strip()]


def says(r, word):
    """True when a line the run printed starts with the verdict word, as `unknown` or `unknown - asks missing` does."""
    return any(re.match(re.escape(word) + r"\b", line) for line in verdict_lines(r))


def error_line(r):
    """The `error:` line argparse prints for a usage error, or None."""
    found = [line.strip() for line in r.stderr.splitlines() if "error:" in line]
    return found[-1] if found else None


def changed_count(r):
    """N of the first `changed N` line the run printed, or None."""
    for line in verdict_lines(r):
        found = re.match(r"changed\s+(\d+)\b", line)
        if found:
            return int(found.group(1))
    return None


def shown(r, secrets=()):
    """The run's output for a failure message, with each secret taken out so a red never prints one."""
    text = r.stdout + r.stderr
    for secret in secrets:
        text = text.replace(secret, "<redacted>")
    return text


def item(n):
    """An item shaped like a fetched one: the same keys, synthetic values."""
    return {"id": "item-%03d" % n, "n": n, "kind": "licence", "status": "open", "title": "Item %d" % n,
            "short": "Item %d" % n, "ref": "R-%03d" % n, "home": "queue", "owner": "Test Owner",
            "added": "2026-10-%02dT09:00:00Z" % (1 + n % 28),
            "context": "Synthetic item %d for the export round trip." % n, "why": "Synthetic reason %d." % n,
            "options": [{"key": k, "label": "Option " + k.upper(), "gain": "Gain", "lose": "Loss", "how": "Pick " + k}
                        for k in "ab"],
            "links": [{"label": "Record", "url": ARTIFACT}], "pick": "a",
            "lastAnswer": {"at": "2026-10-02T10:00:00Z", "note": "Synthetic"}}


def full_size():
    """The full-size export: 120 items, 7 answers, 3 groups, 2 asks and the page's meta. 133 docs in all."""
    items = {"item-%03d" % n: item(n) for n in range(1, 121)}
    answers = {"ans-%02d" % n: {"item": "item-%03d" % n, "pick": "a", "note": "Synthetic answer %d" % n}
               for n in range(1, 8)}
    groups = {"grp-%d" % n: {"name": "Group %d" % n, "items": ["item-%03d" % n]} for n in range(1, 4)}
    asks = {"ask-%d" % n: {"item": "item-%03d" % n, "question": "Which option?"} for n in range(1, 3)}
    return {"items": items, "answers": answers, "groups": groups, "asks": asks, "meta": {"page": META}}


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)  # test-temp-standard: never the system temp dir
        self.addCleanup(self.tmp.cleanup)

    def fetch(self, items=None, answers=None, groups=None, asks=None, meta=None, folders=None):
        """A fetched folder: one folder per collection, each doc a JSON file, and the completeness marker. An empty
        collection is an empty folder with its marker. `folders`, when given, names the folders instead of the five:
        {folder: {doc_id: data}}, for a page whose collections are named by --collections."""
        root = tempfile.mkdtemp(prefix="fetched-", dir=self.tmp.name)
        docs = folders if folders is not None else {"items": items, "answers": answers, "groups": groups,
                                                     "asks": asks, "meta": meta}
        for name, found in docs.items():
            os.makedirs(os.path.join(root, name))
            for doc_id, data in (found or {}).items():
                write_text(os.path.join(root, name, doc_id + ".json"), canonical(data))
            write_text(os.path.join(root, name, MARKER), "")
        return root

    def out(self, name="waiting"):
        return os.path.join(self.tmp.name, name)

    def run_cmd(self, *args, env=None, timeout=60):
        if not os.path.isfile(CMD):
            self.fail("export_page.py is not built: no file at %s" % CMD)
        env = env or dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, CMD, *args], capture_output=True, text=True, timeout=timeout, env=env)

    def export(self, fetched, out, page=None, allow_empty=(), timeout=60):
        args = ["--fetched", fetched, "--out", out]
        if page:
            args += ["--page", page]
        for name in allow_empty:
            args += ["--allow-empty", name]
        return self.run_cmd(*args, timeout=timeout)

    def assertVerdict(self, r, want, secrets=()):
        self.assertTrue(says(r, want), "verdict %r not printed. Output:\n%s" % (want, shown(r, secrets)))

    def assertChanged(self, r, n, secrets=()):
        self.assertEqual(changed_count(r), n, "`changed %d` not printed. Output:\n%s" % (n, shown(r, secrets)))

    def assertBatches(self, r, k, n):
        found = [m for m in (re.match(r"batches\s+(\d+)\s+docs\s+(\d+)\b", line) for line in verdict_lines(r)) if m]
        self.assertTrue(found, "no `batches <k> docs <n>` line. Output:\n" + shown(r))
        self.assertEqual((int(found[0].group(1)), int(found[0].group(2))), (k, n), shown(r))


class Scan(Base):
    def assert_refused(self, label, note, secret):
        fetched = self.fetch(items={"leak": {"id": "leak", "title": "Leak", "note": note}})
        out = self.out()
        before = snapshot(out)
        r = self.export(fetched, out)
        self.assertVerdict(r, "refused", [secret])
        self.assertEqual(r.returncode, 1, "%s: refused must exit 1. Output:\n%s" % (label, shown(r, [secret])))
        self.assertNotIn(secret, r.stdout + r.stderr, "%s: the matched value was printed" % label)
        self.assertEqual(snapshot(out), before, "%s: a refused run wrote into the copy" % label)

    def test_refuses_each_secret_shape_and_writes_nothing(self):
        for label, note, secret in RED:
            with self.subTest(label=label):
                self.assert_refused(label, note, secret)

    def test_a_secret_as_a_doc_id_is_refused_and_never_printed(self):
        # A doc's file name is its id, so a secret there is a find too. The find's line names the doc with the id redacted.
        cases = (("email as a doc id", "person.name" + "@" + "example.com"), ("token as a doc id", "ghp_" + TAIL))
        for index, (label, doc_id) in enumerate(cases):
            with self.subTest(label=label):
                fetched = self.fetch(items={doc_id: {"id": "x", "title": "Ok"}})
                out = self.out("doc-id-%d" % index)
                before = snapshot(out)
                r = self.export(fetched, out)
                self.assertVerdict(r, "refused", [doc_id])
                self.assertEqual(r.returncode, 1, shown(r, [doc_id]))
                self.assertNotIn(doc_id, r.stdout + r.stderr, "%s: the id was printed" % label)
                self.assertEqual(snapshot(out), before, "%s: a refused run wrote into the copy" % label)

    def test_each_find_is_one_line_that_names_its_file_and_field(self):
        note = "ok " + "sk-ant-" + "aB3" * 12
        fetched = self.fetch(items={"leak": {"id": "leak", "title": "ghp_" + TAIL, "note": note}})
        r = self.export(fetched, self.out())
        self.assertVerdict(r, "refused", [TAIL])
        finds = [line for line in (r.stdout + r.stderr).splitlines() if "leak" in line]
        self.assertEqual(sum("title" in line for line in finds), 1, "no one line names the title field:\n" + shown(r, [TAIL]))
        self.assertEqual(sum("note" in line for line in finds), 1, "no one line names the note field:\n" + shown(r, [TAIL]))

    def test_words_and_shapes_that_are_not_secrets_pass(self):
        for index, (label, value) in enumerate(GREEN):
            with self.subTest(label=label):
                doc = {"id": "ok", "title": "Ok", "note": value}
                out = self.out("waiting-%d" % index)
                r = self.export(self.fetch(items={"ok": doc}), out)
                self.assertFalse(says(r, "refused"), "%s: the scan refused a non-secret. Output:\n%s" % (label, shown(r)))
                self.assertEqual(r.returncode, 0, "%s: the run failed without a refusal. Output:\n%s" % (label, shown(r)))
                self.assertEqual(read_text(os.path.join(out, "items", "ok.json")), canonical(doc), label)

    def timed_export(self, fetched, folder, timeout, want_exit=0):
        """Seconds for one export of `fetched` into a fresh copy. The exit code is asserted before the time is used:
        0 for an export, 1 for a refusal (`want_exit`)."""
        start = time.perf_counter()
        r = self.export(fetched, self.out(folder), timeout=timeout)
        took = time.perf_counter() - start
        cause = "was not refused" if want_exit else "did not export"
        self.assertEqual(r.returncode, want_exit, "%s %s (exit %d). Output:\n%s" % (folder, cause, r.returncode, shown(r)))
        return took

    def timed_growth(self, folder, make_note, want_exit=0):
        """(growth, short, long) for the scan of a run of 4 x RUN_N characters over the scan of a run of RUN_N, both timed
        in this process. Each size is the faster of two exports, so one slow export does not set the ratio. The timeout is
        a hang guard only: the scan takes well under a second at RUN_N, and a quadratic scan takes minutes at 4 x RUN_N."""
        timings = {}
        for size in (RUN_N, 4 * RUN_N):
            fetched = self.fetch(items={"ok": {"id": "ok", "title": "Ok", "note": make_note(size)}})
            timings[size] = min(self.timed_export(fetched, "%s-%d-%d" % (folder, size, run), timeout=900, want_exit=want_exit)
                                for run in (1, 2))
        return timings[4 * RUN_N] / timings[RUN_N], timings[RUN_N], timings[4 * RUN_N]

    def assert_grows_no_faster_than_linear(self, folder, make_note, what, want_exit=0):
        growth, short, long_run = self.timed_growth(folder, make_note, want_exit)
        self.assertLess(growth, GROWTH_BOUND,
                        "the scan of %s grew %.1f times, from %.3f s at %d characters to %.3f s at %d; a linear scan "
                        "grows 4 times, and the bound is %d" % (what, growth, short, RUN_N, long_run, 4 * RUN_N, GROWTH_BOUND))

    def test_a_long_run_of_name_characters_grows_no_faster_than_linear(self):
        # Name characters with no keyword in them.
        self.assert_grows_no_faster_than_linear("long-run", lambda n: "aB3_-" * (n // 5), "a run of name characters")

    def test_a_long_run_of_underscores_grows_no_faster_than_linear(self):
        # The password shape's name prefix takes `_`, so a run of them is re-read from each start position.
        self.assert_grows_no_faster_than_linear("underscores", lambda n: "_" * n, "a run of underscores")

    def test_a_long_run_of_key_equals_grows_no_faster_than_linear(self):
        # The credential-name value lookaheads scan to the end of a run of `key=`, from each start position.
        self.assert_grows_no_faster_than_linear("key-equals", lambda n: "key=" * (n // 4), "a run of key=")

    def test_a_digit_past_index_256_is_refused_and_grows_no_faster_than_linear(self):
        # A same-process ratio, as above (test-practices P5): stdlib `re` exposes no step count to pin instead. Each size's only
        # digit is past index 256, so each export must refuse it. A build that passes it goes red on the refusal, first.
        self.assert_grows_no_faster_than_linear(
            "digit-past-256", lambda n: "API_KEY=" + "abcdefgh" * (n // 8) + "1",
            "a credential value whose only digit is past index 256", want_exit=1)


class Mirror(Base):
    def test_counts_each_write_and_delete_and_keeps_the_rest(self):
        fetched = self.fetch(items={"a": {"id": "a"}, "b": {"id": "b"}, "c": {"id": "c"}},
                             answers={"x": {"id": "x"}}, meta={"page": META})
        out = self.out()
        self.assertChanged(self.export(fetched, out), 5)
        c_path = os.path.join(out, "items", "c.json")
        os.utime(c_path, (SENTINEL, SENTINEL))
        write_text(os.path.join(fetched, "items", "a.json"), canonical({"id": "a", "title": "new"}))
        write_text(os.path.join(fetched, "items", "d.json"), canonical({"id": "d"}))
        os.remove(os.path.join(fetched, "items", "b.json"))
        r = self.export(fetched, out)
        self.assertChanged(r, 3)
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(os.stat(c_path).st_mtime, SENTINEL, "an unchanged doc was rewritten")
        self.assertFalse(os.path.exists(os.path.join(out, "items", "b.json")), "a doc no longer fetched was kept")
        self.assertEqual(read_text(os.path.join(out, "items", "a.json")), canonical({"id": "a", "title": "new"}))
        self.assertEqual(read_text(os.path.join(out, "items", "d.json")), canonical({"id": "d"}))

    def test_each_written_doc_is_canonical_json(self):
        fetched = self.fetch(items={"a": {"z": 1, "a": ["uni", 2]}}, meta={"page": META})
        out = self.out()
        self.assertEqual(self.export(fetched, out).returncode, 0)
        self.assertEqual(read_text(os.path.join(out, "items", "a.json")), canonical({"z": 1, "a": ["uni", 2]}))
        self.assertEqual(read_text(os.path.join(out, "meta", "page.json")), canonical(META))

    def test_an_items_doc_with_no_id_field_exports_under_its_key_unchanged(self):
        """The doc key is the item's id, so an items doc with no `id` field lands at items/<key>.json as it was fetched.
        Green on the old code too. Renumber reads only an item's `n`. The page check reads `id` only for a held picture
        with no whole-number `n`. This item has no picture, and its `n` is whole, so neither reads its `id`."""
        data = {"n": 29, "kind": "decision", "status": "open", "title": "No id field", "options": [{"key": "a", "label": "A"}]}
        fetched = self.fetch(items={"k29": data}, meta={"page": META})
        out = self.out()
        r = self.export(fetched, out)
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(read_text(os.path.join(out, "items", "k29.json")), canonical(data))

    def test_a_rewrite_with_the_same_data_is_same(self):
        fetched = self.fetch(items={"a": {"id": "a", "n": 2}})
        out = self.out()
        self.export(fetched, out)
        self.assertVerdict(self.export(fetched, out), "same")
        # The same data, fetched again in another layout: the copy's bytes do not follow the fetch's layout.
        write_text(os.path.join(fetched, "items", "a.json"), json.dumps({"n": 2, "id": "a"}, indent=4))
        r = self.export(fetched, out)
        self.assertVerdict(r, "same")
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(read_text(os.path.join(out, "items", "a.json")), canonical({"id": "a", "n": 2}))

    def test_an_emptied_collection_is_unknown_unless_the_session_allows_it(self):
        fetched = self.fetch(items={"a": {"id": "a"}, "b": {"id": "b"}, "c": {"id": "c"}})
        out = self.out()
        self.assertChanged(self.export(fetched, out), 3)
        for name in ("a", "b", "c"):
            os.remove(os.path.join(fetched, "items", name + ".json"))
        before = snapshot(out)
        r = self.export(fetched, out)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertEqual(snapshot(out), before, "an emptied collection was deleted without --allow-empty")
        r = self.export(fetched, out, allow_empty=("asks",))
        self.assertVerdict(r, "unknown")
        self.assertEqual(snapshot(out), before, "--allow-empty for another collection deleted docs")
        r = self.export(fetched, out, allow_empty=("items",))
        self.assertChanged(r, 3)
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(glob.glob(os.path.join(out, "items", "*.json")), [], "the allowed empty collection kept docs")

    def test_a_collection_without_its_completeness_marker_is_unknown_and_writes_nothing(self):
        fetched = self.fetch(items={"a": {"id": "a"}}, meta={"page": META})
        os.remove(os.path.join(fetched, "asks", MARKER))
        out = self.out()
        write_text(os.path.join(out, "items", "old.json"), "{}\n")
        before = snapshot(out)
        r = self.export(fetched, out)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertEqual(snapshot(out), before, "a fetch with no completeness marker wrote into the copy")

    def test_a_fetch_with_no_completeness_markers_is_unknown_and_writes_nothing(self):
        fetched = self.fetch(items={"a": {"id": "a"}}, meta={"page": META})
        for name in COLLECTIONS:
            os.remove(os.path.join(fetched, name, MARKER))
        out = self.out()
        write_text(os.path.join(out, "items", "old.json"), "{}\n")
        before = snapshot(out)
        r = self.export(fetched, out)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertEqual(snapshot(out), before, "a fetch with no completeness marker at all wrote into the copy")

    def test_all_empty_collections_into_an_empty_copy_are_same(self):
        fetched = self.fetch()
        out = self.out()
        r = self.export(fetched, out)
        self.assertVerdict(r, "same")
        self.assertEqual(r.returncode, 0, shown(r))

    def test_a_missing_collection_folder_is_unknown_and_writes_nothing(self):
        fetched = self.fetch(items={"a": {"id": "a"}}, meta={"page": META})
        shutil.rmtree(os.path.join(fetched, "asks"))
        out = self.out()
        write_text(os.path.join(out, "items", "old.json"), "{}\n")
        before = snapshot(out)
        r = self.export(fetched, out)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertEqual(snapshot(out), before, "a run with a missing folder wrote into the copy")

    def test_a_refused_fetch_writes_nothing_and_keeps_the_old_copy(self):
        out = self.out()
        self.assertEqual(self.export(self.fetch(items={"a": {"id": "a", "t": "old"}, "c": {"id": "c"}}), out).returncode, 0)
        before = snapshot(out)
        # "z" sorts last, so a run that wrote as it read would change "a" before it reached the token.
        fetched = self.fetch(items={"a": {"id": "a", "t": "new"}, "c": {"id": "c"}, "z": {"id": "z", "note": "ghp_" + TAIL}})
        r = self.export(fetched, out)
        self.assertVerdict(r, "refused", [TAIL])
        self.assertEqual(r.returncode, 1, shown(r, [TAIL]))
        self.assertEqual(snapshot(out), before, "a refused fetch changed the old copy")

    def test_a_crash_exits_3_with_one_unknown_line(self):
        fetched = self.fetch(meta={"page": META})
        write_text(os.path.join(fetched, "items", "deep.json"), DEEP)  # raw text: canonical() would crash the test too
        r = self.export(fetched, self.out())
        self.assertEqual(r.returncode, 3, "a crash must exit 3, not %d. Output:\n%s" % (r.returncode, shown(r)))
        lines = verdict_lines(r)
        self.assertEqual(len(lines), 1, "a crash must print one unknown line. Output:\n" + shown(r))
        self.assertTrue(lines[0].startswith("unknown"), shown(r))

    def test_runs_with_no_git_on_the_path(self):
        fetched = self.fetch(items={"a": {"id": "a"}})
        empty = os.path.join(self.tmp.name, "no-bin")  # a PATH with no git in it
        os.makedirs(empty)
        out = self.out()
        r = self.run_cmd("--fetched", fetched, "--out", out, env=dict(os.environ, PATH=empty, PYTHONDONTWRITEBYTECODE="1"))
        self.assertChanged(r, 1)
        self.assertEqual(r.returncode, 0, shown(r))


class Page(Base):
    def test_design_block_lands_in_page_designdata(self):
        page = write_text(os.path.join(self.tmp.name, "page.html"), DESIGN.sub(lambda m: m.group(1) + DESIGN_BODY + m.group(3), PAGE, count=1))
        out = self.out()
        r = self.export(self.fetch(meta={"page": META}), out, page=page)
        self.assertEqual(r.returncode, 0, shown(r))
        with open(os.path.join(out, "page", "designData.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), json.loads(DESIGN_BODY), "the page's designData did not land as the block's JSON")

    def test_a_page_with_no_designdata_block_is_unknown(self):
        page = write_text(os.path.join(self.tmp.name, "page.html"), PAGE.replace(DESIGN_ELEMENT, "", 1))
        r = self.export(self.fetch(meta={"page": META}), self.out(), page=page)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_page_with_two_designdata_blocks_is_unknown(self):
        page = write_text(os.path.join(self.tmp.name, "page.html"), PAGE + DESIGN_ELEMENT)
        r = self.export(self.fetch(meta={"page": META}), self.out(), page=page)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_token_in_designdata_refuses_the_whole_export(self):
        body = '{"a": "' + "ghp_" + TAIL + '"}'
        page = write_text(os.path.join(self.tmp.name, "page.html"), DESIGN.sub(lambda m: m.group(1) + body + m.group(3), PAGE, count=1))
        out = self.out()
        before = snapshot(out)
        r = self.export(self.fetch(meta={"page": META}), out, page=page)
        self.assertVerdict(r, "refused", [TAIL])
        self.assertEqual(r.returncode, 1, shown(r, [TAIL]))
        self.assertNotIn(TAIL, r.stdout + r.stderr, "the matched value was printed")
        self.assertEqual(snapshot(out), before, "a refused page changed the copy")

    def test_a_mockup_change_counts_designdata_and_the_page_html(self):
        # designData.json and page.html both hold the mockup, so one mockup change writes two files.
        first = write_text(os.path.join(self.tmp.name, "page-first.html"), DESIGN.sub(lambda m: m.group(1) + DESIGN_BODY + m.group(3), PAGE, count=1))
        second = write_text(os.path.join(self.tmp.name, "page-second.html"),
                            DESIGN.sub(lambda m: m.group(1) + '{"a": "changed mockup"}' + m.group(3), PAGE, count=1))
        fetched = self.fetch(meta={"page": META})
        out = self.out()
        self.assertEqual(self.export(fetched, out, page=first).returncode, 0)
        r = self.export(fetched, out, page=second)
        self.assertChanged(r, 2)
        self.assertEqual(r.returncode, 0, shown(r))

    def test_the_page_lands_at_page_html_byte_identical(self):
        page = write_bytes(os.path.join(self.tmp.name, "page.html"), PAGE_BYTES)
        out = self.out()
        r = self.export(self.fetch(meta={"page": META}), out, page=page)
        self.assertVerdict(r, "changed")
        self.assertEqual(r.returncode, 0, shown(r))
        landed = os.path.join(out, "page", "page.html")
        self.assertTrue(os.path.isfile(landed), "page/page.html was not written. Output:\n" + shown(r))
        self.assertEqual(read_bytes(landed), PAGE_BYTES, "page/page.html is not byte-identical to the page (CRLF or non-ASCII changed)")

    def test_a_full_size_page_lands_byte_identical_with_its_full_database(self):
        page = write_bytes(os.path.join(self.tmp.name, "page.html"), BIG_PAGE)
        out = self.out()
        r = self.export(self.fetch(**full_size()), out, page=page)
        self.assertVerdict(r, "changed")
        self.assertEqual(r.returncode, 0, shown(r))
        landed = os.path.join(out, "page", "page.html")
        self.assertTrue(os.path.isfile(landed), "page/page.html was not written for the full-size page")
        self.assertEqual(read_bytes(landed), BIG_PAGE, "the full-size page/page.html is not byte-identical")

    def test_an_empty_database_still_lands_its_page(self):
        page = write_bytes(os.path.join(self.tmp.name, "page.html"), PAGE_BYTES)
        out = self.out()
        r = self.export(self.fetch(), out, page=page)
        self.assertVerdict(r, "changed")
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertTrue(os.path.isfile(os.path.join(out, "page", "page.html")), "page/page.html was not written with an empty database")
        self.assertEqual(read_bytes(os.path.join(out, "page", "page.html")), PAGE_BYTES)

    def test_a_second_run_with_the_same_page_is_same_and_rewrites_nothing(self):
        page = write_bytes(os.path.join(self.tmp.name, "page.html"), PAGE_BYTES)
        fetched = self.fetch(meta={"page": META})
        out = self.out()
        self.assertEqual(self.export(fetched, out, page=page).returncode, 0)
        landed = os.path.join(out, "page", "page.html")
        self.assertTrue(os.path.isfile(landed), "page/page.html was not written by the first run")
        os.utime(landed, (SENTINEL, SENTINEL))
        before = snapshot(out)
        r = self.export(fetched, out, page=page)
        self.assertVerdict(r, "same")
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(os.stat(landed).st_mtime, SENTINEL, "an unchanged page/page.html was rewritten")
        self.assertEqual(snapshot(out), before, "a second run with the same page wrote into the copy")

    def test_a_changed_page_counts_in_changed_n(self):
        first = write_bytes(os.path.join(self.tmp.name, "page-first.html"), PAGE_BYTES)
        second = write_bytes(os.path.join(self.tmp.name, "page-second.html"), REVISED_PAGE)
        fetched = self.fetch(meta={"page": META})
        out = self.out()
        self.assertEqual(self.export(fetched, out, page=first).returncode, 0)
        r = self.export(fetched, out, page=second)
        self.assertChanged(r, 1)
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertEqual(read_bytes(os.path.join(out, "page", "page.html")), REVISED_PAGE, "the changed page did not land")


class PageScan(Base):
    """The page's HTML is scanned as text with the docs' shapes, before any write."""

    def test_a_secret_in_the_page_text_refuses_the_export_and_writes_nothing(self):
        for index, (label, snippet, secret) in enumerate(page_snippets()):
            with self.subTest(label=label):
                html = page_with(snippet)
                self.assertEqual(html.count(secret), 1, "fixture: the secret must sit once in the page")
                self.assertNotIn(secret, DESIGN_ELEMENT, "fixture: the secret must sit outside the designData block")
                page = write_text(os.path.join(self.tmp.name, "page-%d.html" % index), html)
                out = self.out("refused-%d" % index)
                r = self.export(self.fetch(meta={"page": META}), out, page=page)
                self.assertVerdict(r, "refused", [secret])
                self.assertEqual(r.returncode, 1, "%s: refused must exit 1. Output:\n%s" % (label, shown(r, [secret])))
                self.assertNotIn(secret, r.stdout + r.stderr, "%s: the matched value was printed" % label)
                self.assertEqual(snapshot(out), {}, "%s: a refused page wrote into the copy" % label)

    def test_a_refused_page_keeps_the_old_copy(self):
        out = self.out()
        clean = write_bytes(os.path.join(self.tmp.name, "page-clean.html"), PAGE_BYTES)
        self.assertEqual(self.export(self.fetch(meta={"page": META}), out, page=clean).returncode, 0)
        before = snapshot(out)
        leaky = write_text(os.path.join(self.tmp.name, "page-leaky.html"), page_with("<p>Token: %s</p>\n" % TOKEN))
        r = self.export(self.fetch(meta={"page": META}, items={"a": {"id": "a", "n": 2}}), out, page=leaky)
        self.assertVerdict(r, "refused", [TOKEN])
        self.assertEqual(r.returncode, 1, shown(r, [TOKEN]))
        self.assertNotIn(TOKEN, r.stdout + r.stderr, "the matched value was printed")
        self.assertEqual(snapshot(out), before, "a refused page changed the old copy")

    def test_cdn_script_tags_and_prose_punctuation_are_not_refused(self):
        cases = (("CDN script tags", CDN_SNIPPET), ("comment openers and a lone quote in prose", PROSE_SNIPPET),
                 ("an IP host with no credentials", IP_LINK_SNIPPET))
        for index, (label, snippet) in enumerate(cases):
            with self.subTest(label=label):
                page = write_text(os.path.join(self.tmp.name, "green-%d.html" % index), page_with(snippet))
                r = self.export(self.fetch(meta={"page": META}), self.out("green-%d" % index), page=page)
                self.assertFalse(says(r, "refused"), "%s: the page was refused. Output:\n%s" % (label, shown(r)))
                self.assertVerdict(r, "changed")
                self.assertEqual(r.returncode, 0, "%s: a non-secret page failed. Output:\n%s" % (label, shown(r)))

    def test_digit_led_email_domains_in_the_page_text_still_refuse(self):
        for index, address in enumerate(("jane@1st.example.com", "jane@12.34.example.com", "jane@1.2.3.com")):
            with self.subTest(address=address):
                page = write_text(os.path.join(self.tmp.name, "digit-%d.html" % index), page_with("<p>Contact %s</p>\n" % address))
                out = self.out("digit-%d" % index)
                r = self.export(self.fetch(meta={"page": META}), out, page=page)
                self.assertVerdict(r, "refused", [address])
                self.assertEqual(r.returncode, 1, "%s: a personal email was not refused. Output:\n%s" % (address, shown(r, [address])))
                self.assertNotIn(address, r.stdout + r.stderr, "%s: the address was printed" % address)
                self.assertEqual(snapshot(out), {}, "%s: a refused page wrote into the copy" % address)

    def test_retina_names_in_the_page_text_are_not_emails(self):
        srcset = '<img srcset="logo@2x.png 2x" src="icon@3x.png" alt="">\n'
        want = page_with(srcset).encode("utf-8")
        page = write_bytes(os.path.join(self.tmp.name, "page-retina.html"), want)
        out = self.out()
        r = self.export(self.fetch(meta={"page": META}), out, page=page)
        self.assertFalse(says(r, "refused"), "retina names in the page text were refused as emails. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertVerdict(r, "changed")
        self.assertEqual(read_bytes(os.path.join(out, "page", "page.html")), want, "the page with retina names is not byte-identical")

    def test_an_email_at_a_retina_looking_domain_still_refuses(self):
        address = "jane@2x.com"
        page = write_text(os.path.join(self.tmp.name, "page-2x.html"), page_with("<p>Contact %s</p>\n" % address))
        out = self.out()
        r = self.export(self.fetch(meta={"page": META}), out, page=page)
        self.assertVerdict(r, "refused", [address])
        self.assertEqual(r.returncode, 1, "jane@2x.com was not refused as an email. Output:\n" + shown(r, [address]))
        self.assertNotIn(address, r.stdout + r.stderr, "the address was printed")
        self.assertEqual(snapshot(out), {}, "a refused page wrote into the copy")


def item_as(doc_id, n):
    """`item(n)` under another doc id. The item's `id` field follows the doc id, as the page's own items do."""
    return dict(item(n), id=doc_id)


def answer_for(item_id, n):
    """An answer keyed by its item's id, read as page_grant.py reads it: `item` is that id and `n` is the item's n."""
    return {"item": item_id, "n": n, "pick": "a", "note": "Synthetic answer for %s" % item_id}


class Rebuild(Base):
    def batch_entries(self, batches):
        files = sorted(glob.glob(os.path.join(batches, "batch-*.json")))
        entries, sizes = [], []
        for path in files:
            with open(path, encoding="utf-8") as f:
                batch = json.load(f)
            self.assertIsInstance(batch, list, os.path.basename(path))
            sizes.append(len(batch))
            entries.extend(batch)
        return files, entries, sizes

    def rebuild(self, waiting, batches, collections=()):
        os.makedirs(batches, exist_ok=True)
        args = ["--rebuild", waiting, "--batches", batches]
        if collections:
            args += ["--collections", *collections]
        return self.run_cmd(*args)

    def copy_of(self, folders, name="copy"):
        """A copy of a registry artifact: `folders` maps each folder name to {doc_id: data}, and each doc is written as
        `<doc_id>.json`, as an export holds it. A rebuild reads no marker, so none is written. An empty folder is kept."""
        root = self.out(name)
        for folder, docs in folders.items():
            os.makedirs(os.path.join(root, folder), exist_ok=True)
            for doc_id, data in docs.items():
                write_text(os.path.join(root, folder, doc_id + ".json"), canonical(data))
        return root

    def assertOptionBuilt(self, r):
        """The script knows --collections. argparse rejects an option it does not know, so this red names the cause."""
        self.assertNotIn("unrecognized arguments", shown(r), "the option is not built: argparse rejects --collections")

    def assertUnknownNames(self, r, folder):
        """Exit 2 and an `unknown` line that names `folder` as neither a named collection nor page/."""
        self.assertEqual(r.returncode, 2, shown(r))
        lines = [line for line in verdict_lines(r) if line.startswith("unknown")]
        self.assertTrue(any(("/%s is neither" % folder) in line for line in lines),
                        "no unknown line names the folder %s. Output:\n%s" % (folder, shown(r)))

    def exported(self, docs, page=True):
        fetched = self.fetch(**docs)
        waiting = self.out()
        page_path = write_text(os.path.join(self.tmp.name, "page.html"), DESIGN.sub(lambda m: m.group(1) + DESIGN_BODY + m.group(3), PAGE, count=1))
        r = self.export(fetched, waiting, page=page_path if page else None)
        self.assertEqual(r.returncode, 0, shown(r))
        return waiting

    def test_round_trip_of_a_full_size_export_is_exact(self):
        data = full_size()
        waiting = self.exported(data)
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches)
        self.assertEqual(r.returncode, 0, shown(r))
        files, entries, sizes = self.batch_entries(batches)
        self.assertBatches(r, len(files), 133)
        self.assertTrue(all(size <= 50 for size in sizes), "a batch holds more than 50 entries: %s" % sizes)
        for entry in entries:
            self.assertEqual(set(entry), {"op", "collection", "doc_id", "data"}, "an entry has the wrong keys")
            self.assertEqual(entry["op"], "set")
        self.assertNotIn("page", {entry["collection"] for entry in entries}, "the page folder went into a batch")
        want = collections.Counter((name, doc_id, canonical(doc)) for name, docs in data.items()
                                   for doc_id, doc in docs.items())
        got = collections.Counter((e["collection"], e["doc_id"], canonical(e["data"])) for e in entries)
        self.assertEqual(len(entries), 133, "the batches hold %d entries, not 133" % len(entries))
        self.assertEqual(set(got), set(want), "the batches' docs are not the export's docs")
        self.assertEqual(max(got.values()), 1, "a doc is in the batches more than once")

    def test_fifty_docs_fit_one_batch(self):
        waiting = self.exported({"items": {"item-%03d" % n: item(n) for n in range(1, 51)}}, page=False)
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches)
        self.assertBatches(r, 1, 50)
        self.assertEqual(self.batch_entries(batches)[2], [50])

    def test_fifty_one_docs_split_in_two(self):
        waiting = self.exported({"items": {"item-%03d" % n: item(n) for n in range(1, 52)}}, page=False)
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches)
        self.assertBatches(r, 2, 51)
        files, entries, sizes = self.batch_entries(batches)
        self.assertEqual(len(files), 2)
        self.assertTrue(all(size <= 50 for size in sizes), sizes)
        self.assertEqual(sorted(e["doc_id"] for e in entries), sorted("item-%03d" % n for n in range(1, 52)))

    def test_a_batch_stays_under_900_kb(self):
        # 100 docs of about 20 KB: 50 of them would be about 1 MB, so the size cap splits them too. 900 KB is read as 900,000 bytes.
        big = {"item-%03d" % n: dict(item(n), context="word " * 4000) for n in range(1, 101)}
        waiting = self.exported({"items": big}, page=False)
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches)
        self.assertEqual(r.returncode, 0, shown(r))
        files, entries, _ = self.batch_entries(batches)
        self.assertGreaterEqual(len(files), 3, "2 MB of docs cannot fit in fewer than three 900 KB batches")
        for path in files:
            self.assertLessEqual(os.path.getsize(path), 900000, "%s is over 900 KB" % os.path.basename(path))
        self.assertEqual(len(entries), 100)
        self.assertBatches(r, len(files), 100)

    def test_a_doc_over_900_kb_is_unknown(self):
        waiting = self.exported({"items": {"item-001": dict(item(1), context="word " * 200000)}}, page=False)
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"))
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_folder_that_is_not_a_collection_is_refused(self):
        waiting = self.exported({"items": {"item-001": item(1)}}, page=False)
        write_text(os.path.join(waiting, "stray", "x.json"), canonical({"id": "x"}))
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"))
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_crash_in_rebuild_exits_3_with_one_unknown_line(self):
        waiting = self.exported({"items": {"item-001": item(1)}}, page=False)
        # 100,000 levels: json.load raises RecursionError inside rebuild, and no Stop handler takes it, so it is a crash.
        write_text(os.path.join(waiting, "items", "deep.json"), "[" * 100000 + "]" * 100000)
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"))
        self.assertEqual(r.returncode, 3, "a crash must exit 3, not %d. Output:\n%s" % (r.returncode, shown(r)))
        lines = verdict_lines(r)
        self.assertEqual(len(lines), 1, "a crash must print one unknown line. Output:\n" + shown(r))
        self.assertTrue(lines[0].startswith("unknown"), shown(r))

    def test_an_empty_waiting_dir_is_unknown(self):
        waiting = self.out()
        os.makedirs(waiting)
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"))
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_a_missing_waiting_dir_is_unknown(self):
        r = self.rebuild(self.out(), os.path.join(self.tmp.name, "batches"))
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))

    def test_named_collections_rebuild_their_docs_under_their_folder_names(self):
        # 30 + 30 docs need two batches of at most 50. `receipts` is named but has no folder: it is empty, not unknown.
        steps = {"step-%03d" % n: {"n": n, "title": "Step %d" % n} for n in range(1, 31)}
        topics = {"topic-%03d" % n: {"n": n, "title": "Topic %d" % n} for n in range(1, 31)}
        waiting = self.copy_of({"steps": steps, "topics": topics})
        write_text(os.path.join(waiting, "page", "page.html"), "<!doctype html>\n<title>registry</title>\n")
        write_text(os.path.join(waiting, "page", "files", "x.css"), "body {}\n")
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(waiting, batches, collections=("steps", "topics", "receipts"))
        self.assertOptionBuilt(r)
        self.assertEqual(r.returncode, 0, shown(r))
        files, entries, sizes = self.batch_entries(batches)
        self.assertEqual(len(files), 2, "60 docs in batches of at most 50 make two batches, not %d" % len(files))
        self.assertBatches(r, 2, 60)
        for entry in entries:
            self.assertEqual(set(entry), {"op", "collection", "doc_id", "data"}, "an entry has the wrong keys")
            self.assertEqual(entry["op"], "set")
        self.assertEqual({entry["collection"] for entry in entries}, {"steps", "topics"},
                         "the batches name a collection other than the two folders that exist")
        want = collections.Counter([("steps", doc_id, canonical(doc)) for doc_id, doc in steps.items()]
                                   + [("topics", doc_id, canonical(doc)) for doc_id, doc in topics.items()])
        got = collections.Counter((e["collection"], e["doc_id"], canonical(e["data"])) for e in entries)
        self.assertEqual(got, want, "the batches do not hold each named folder's docs under its folder name")

    def test_a_folder_not_named_with_collections_is_unknown_and_exits_2(self):
        waiting = self.copy_of({"steps": {"step-001": {"n": 1}}, "topics": {"topic-001": {"n": 1}}})
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"), collections=("steps",))
        self.assertOptionBuilt(r)
        self.assertUnknownNames(r, "topics")

    def test_named_collections_replace_the_five_so_a_waiting_folder_not_named_is_unknown(self):
        waiting = self.copy_of({"items": {"item-001": item(1)}, "steps": {"step-001": {"n": 1}}})
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"), collections=("steps",))
        self.assertOptionBuilt(r)
        self.assertUnknownNames(r, "items")

    def test_without_collections_a_non_waiting_folder_is_still_unknown(self):
        waiting = self.copy_of({"steps": {"step-001": {"n": 1}}})
        r = self.rebuild(waiting, os.path.join(self.tmp.name, "batches"))
        self.assertUnknownNames(r, "steps")

    def test_collections_without_rebuild_is_a_usage_error_that_names_rebuild(self):
        fetched, out = self.fetch(), self.out()
        forms = {
            "export mode": ["--fetched", fetched, "--out", out, "--collections", "steps"],
            "batches without rebuild": ["--batches", os.path.join(self.tmp.name, "batches"), "--collections", "steps"],
        }
        for label, args in forms.items():
            with self.subTest(form=label):
                r = self.run_cmd(*args)
                self.assertOptionBuilt(r)
                self.assertEqual(r.returncode, 2, shown(r))
                err = error_line(r)
                self.assertIsNotNone(err, "no usage error line. Output:\n" + shown(r))
                self.assertIn("--rebuild", err, "the usage error does not name --rebuild: %s" % err)
        self.assertFalse(os.path.exists(out), "a usage error wrote the export folder")

    def test_a_collection_name_that_is_not_a_slug_is_a_usage_error(self):
        waiting = self.copy_of({"steps": {"step-001": {"n": 1}}})
        names = [("../steps",), ("a/b",), (".hidden",), ("",), ("steps", "a b")]
        for number, bad in enumerate(names):
            batches = os.path.join(self.tmp.name, "batches-%d" % number)
            with self.subTest(names=bad):
                r = self.rebuild(waiting, batches, collections=bad)
                self.assertOptionBuilt(r)
                self.assertEqual(r.returncode, 2, shown(r))
                self.assertIsNotNone(error_line(r), "a name that is not a slug is not a usage error. Output:\n" + shown(r))
                self.assertEqual(glob.glob(os.path.join(batches, "batch-*.json")), [], "a bad name still wrote batches")

    def test_the_reserved_page_folder_name_is_a_usage_error_that_writes_nothing(self):
        waiting = self.copy_of({"steps": {"step-001": {"n": 1}}})
        write_text(os.path.join(waiting, "page", "page.html"), "<!doctype html>\n<title>registry</title>\n")
        for number, names in enumerate((("page",), ("steps", "page"))):
            batches = os.path.join(self.tmp.name, "batches-%d" % number)
            with self.subTest(names=names):
                r = self.rebuild(waiting, batches, collections=names)
                self.assertOptionBuilt(r)
                self.assertEqual(r.returncode, 2,
                                 "--collections page is not a usage error: exit 2 expected. Output:\n" + shown(r))
                err = error_line(r)
                self.assertIsNotNone(err, "--collections page has no usage error line. Output:\n" + shown(r))
                self.assertIn("'page'", err, "the usage error does not name page: %s" % err)
                self.assertEqual(os.listdir(batches), [], "--collections page still wrote files")


    # --merge: the copy's docs that the live page lacks, as set entries. The contract is in the module docstring.
    def merge_run(self, copy, live, batches, collections=(), live_page=None):
        """`--merge COPY --live LIVE --batches OUT`, with --collections and --live-page when given. It makes no batch
        folder itself."""
        args = ["--merge", copy, "--live", live, "--batches", batches]
        if collections:
            args += ["--collections", *collections]
        if live_page:
            args += ["--live-page", live_page]
        return self.run_cmd(*args)

    def copy_with_designs(self, folders, design, name="copy"):
        """A copy of `folders` that also holds the page's designData, as an export writes it at page/designData.json."""
        copy = self.copy_of(folders, name=name)
        write_text(os.path.join(copy, "page", "designData.json"), canonical(design))
        return copy

    def live_page_with(self, design, name="live.html"):
        """The fixture page with its designData block holding `design`, written under the run folder."""
        body = json.dumps(design, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e")
        text = DESIGN.sub(lambda m: m.group(1) + body + m.group(3), PAGE, count=1)
        return write_text(os.path.join(self.tmp.name, name), text)

    def batch_files(self, batches):
        return sorted(glob.glob(os.path.join(batches, "batch-*.json")))

    def assertNoBatches(self, batches, why):
        self.assertEqual(self.batch_files(batches), [], "%s, yet it wrote batch files" % why)

    def assertMergeSummary(self, r, k, n, kept, renumbered, designs=None):
        """Exit 0, and the last stdout line is `batches K docs N kept-live S renumbered R`, then ` designs D`. The four
        counts are checked in every merge. The design count is checked only when `designs` is given: then the suffix
        must be on the line and read D."""
        self.assertEqual(r.returncode, 0, "exit %d, not 0. Output:\n%s" % (r.returncode, shown(r)))
        lines = r.stdout.splitlines()
        last = lines[-1].strip() if lines else ""
        found = re.fullmatch(r"batches (\d+) docs (\d+) kept-live (\d+) renumbered (\d+)(?: designs (\d+))?", last)
        self.assertIsNotNone(found, "the last stdout line is not `batches K docs N kept-live S renumbered R designs D`; "
                                    "it is %r. Output:\n%s" % (last, shown(r)))
        self.assertEqual(tuple(int(g) for g in found.groups()[:4]), (k, n, kept, renumbered),
                         "the summary counts (batches, docs, kept-live, renumbered) differ. Output:\n" + shown(r))
        if designs is not None:
            self.assertIsNotNone(found.group(5), "the last stdout line has no ` designs %d`: %r" % (designs, last))
            self.assertEqual(int(found.group(5)), designs, "the design count differs. Output:\n" + shown(r))

    def entry_of(self, entries, collection, doc_id):
        found = [e for e in entries if e.get("collection") == collection and e.get("doc_id") == doc_id]
        return found[0] if found else None

    def unnumbered(self, data):
        return {key: value for key, value in data.items() if key != "n"}

    def copy_with_a_clash(self, name="copy", id_field=None):
        """A copy whose item-900 holds n 2, which live item-002 holds, with the item's answer. Items 001 to 003 match the
        live page. Live holds n 1 to 3, so the highest n in either folder is 3. With `id_field`, item-900's `id` field and
        its answer's `item` both hold that value instead of the doc key."""
        moved, answer = item_as("item-900", 2), answer_for("item-900", 2)
        if id_field is not None:
            moved, answer = dict(moved, id=id_field), dict(answer, item=id_field)
        return self.copy_of({
            "items": {"item-001": item(1), "item-002": item(2), "item-003": item(3), "item-900": moved},
            "answers": {"item-900": answer}}, name=name)

    def test_merge_without_its_partner_flag_is_a_usage_error_that_names_it(self):
        copy = self.copy_of({"items": {"item-001": item(1)}})
        live = self.fetch()
        batches = os.path.join(self.tmp.name, "batches")
        forms = {
            "no --live": (["--merge", copy, "--batches", batches], "--live"),
            "no --batches": (["--merge", copy, "--live", live], "--batches"),
        }
        for label, (args, flag) in forms.items():
            with self.subTest(form=label):
                r = self.run_cmd(*args)
                err = error_line(r)
                self.assertIsNotNone(err, "no usage error line. Output:\n" + shown(r))
                self.assertIn(flag, err, "the usage error does not name %s: %s" % (flag, err))
                self.assertEqual(r.returncode, 2, shown(r))
                self.assertNoBatches(batches, "a usage error")

    def test_merge_with_a_missing_or_empty_copy_is_unknown_and_writes_nothing(self):
        empty = self.out("empty-copy")
        os.makedirs(empty)
        live = self.fetch(items={"item-001": item(1)})
        for label, copy in (("missing copy", self.out("no-copy")), ("empty copy", empty)):
            batches = os.path.join(self.tmp.name, "batches-" + label.replace(" ", "-"))
            with self.subTest(form=label):
                r = self.merge_run(copy, live, batches)
                self.assertVerdict(r, "unknown")
                self.assertEqual(r.returncode, 2, shown(r))
                self.assertNoBatches(batches, label)

    def test_merge_with_a_missing_live_folder_is_unknown_and_writes_nothing(self):
        copy = self.copy_of({"items": {"item-001": item(1)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, self.out("no-live"), batches)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertNoBatches(batches, "a missing live folder")

    def test_a_live_collection_with_no_marker_is_unknown_and_writes_nothing(self):
        # A fetch cut short leaves a folder with no marker. Its missing docs look absent, so a merge would `set` over
        # live docs that the fetch never reached: item-002 here.
        live = self.fetch(items={"item-001": item(1)})
        os.remove(os.path.join(live, "items", MARKER))
        copy = self.copy_of({"items": {"item-001": item(1), "item-002": item(2)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertNoBatches(batches, "a live collection with no marker")

    def test_merge_with_a_folder_that_is_not_a_collection_on_either_side_is_unknown(self):
        stray = {"x": {"n": 1}}
        forms = {
            "copy": (self.copy_of({"items": {"item-001": item(1)}, "stray": stray}), self.fetch()),
            "live": (self.copy_of({"items": {"item-001": item(1)}}),
                     self.fetch(folders=dict({name: {} for name in COLLECTIONS}, stray=stray))),
        }
        for label, (copy, live) in forms.items():
            batches = os.path.join(self.tmp.name, "batches-" + label)
            with self.subTest(form=label):
                r = self.merge_run(copy, live, batches)
                lines = [line for line in verdict_lines(r) if line.startswith("unknown")]
                self.assertTrue(any("stray" in line for line in lines),
                                "no unknown line names the stray folder in the %s. Output:\n%s" % (label, shown(r)))
                self.assertEqual(r.returncode, 2, shown(r))
                self.assertNoBatches(batches, "a stray folder in the " + label)

    def test_merge_with_nothing_left_to_write_is_unknown_and_writes_nothing(self):
        live = self.fetch(items={"item-001": item(1), "item-002": item(2)})
        copy = self.copy_of({"items": {"item-001": item(1), "item-002": item(2)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertNoBatches(batches, "a copy the live page already holds")

    def test_merge_of_a_full_size_copy_into_an_empty_live_page_writes_every_doc(self):
        data = full_size()
        copy = self.exported(data, page=False)  # no page, so no designData: the merge needs no --live-page here
        live = self.fetch()  # five empty collections, each with its marker
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 3, 133, 0, 0)
        _, entries, sizes = self.batch_entries(batches)
        self.assertTrue(all(size <= 50 for size in sizes), "a batch holds more than 50 entries: %s" % sizes)
        self.assertNotIn("page", {entry["collection"] for entry in entries}, "the page folder went into a batch")
        want = collections.Counter((name, doc_id, canonical(doc)) for name, docs in data.items()
                                   for doc_id, doc in docs.items())
        got = collections.Counter((e["collection"], e["doc_id"], canonical(e["data"])) for e in entries)
        self.assertEqual(got, want, "the batches do not hold the copy's 133 docs, each once")

    def test_merge_writes_only_the_docs_the_live_page_lacks_and_never_a_live_one(self):
        live = self.fetch(items={"item-001": dict(item(1), context="Live text for item 1."),
                                 "item-002": dict(item(2), context="Live text for item 2.")})
        copy = self.copy_of({"items": {"item-001": item(1), "item-002": item(2), "item-003": item(3)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 1, 2, 0)
        _, entries, _ = self.batch_entries(batches)
        self.assertEqual(sorted((e["collection"], e["doc_id"]) for e in entries), [("items", "item-003")],
                         "the batches hold other docs than the one the live page lacks")
        self.assertEqual(canonical(entries[0]["data"]), canonical(item(3)), "items/item-003 is not the copy's doc")

    def test_a_doc_id_the_live_page_holds_in_one_collection_is_still_written_from_another(self):
        group = {"name": "Copy group", "items": ["shared"]}
        live = self.fetch(items={"shared": dict(item_as("shared", 1), context="Live text.")})
        copy = self.copy_of({"items": {"shared": item_as("shared", 1)}, "groups": {"shared": group}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 1, 1, 0)
        _, entries, _ = self.batch_entries(batches)
        self.assertEqual(sorted((e["collection"], e["doc_id"]) for e in entries), [("groups", "shared")],
                         "the key is not the (collection, doc_id) pair: groups/shared was not written")
        self.assertEqual(canonical(entries[0]["data"]), canonical(group))

    def test_a_copy_answer_whose_item_the_live_page_holds_is_not_written_and_counts_as_kept_live(self):
        # The live page wins on the item, open or answered, so its copy answer is kept. The copy's item-002 is new.
        forms = {
            "open": {},
            "answered": {"answers": {"item-001": dict(answer_for("item-001", 1), note="Owner's answer")}},
        }
        for label, live_answers in forms.items():
            batches = os.path.join(self.tmp.name, "batches-" + label)
            with self.subTest(form=label):
                live = self.fetch(items={"item-001": item(1)}, **live_answers)
                copy = self.copy_of({"items": {"item-001": item(1), "item-002": item(2)},
                                     "answers": {"item-001": answer_for("item-001", 1)}})
                r = self.merge_run(copy, live, batches)
                self.assertMergeSummary(r, 1, 1, 2, 0)
                _, entries, _ = self.batch_entries(batches)
                self.assertEqual(sorted((e["collection"], e["doc_id"]) for e in entries), [("items", "item-002")],
                                 "answers/item-001 was written though items/item-001 is live: the live page must win")

    def test_merge_with_a_live_page_adds_the_copy_design_keys_the_live_page_lacks(self):
        live = self.fetch(items={"item-001": item(1)})
        live_page = self.live_page_with({"a": "live a", "b": "live b"})
        copy = self.copy_with_designs({"items": {"item-002": item(2)}}, {"b": "copy b", "c": "copy c"})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches, live_page=live_page)
        self.assertMergeSummary(r, 1, 1, 0, 0, designs=1)
        design_file = os.path.join(batches, "designData.json")
        self.assertTrue(os.path.isfile(design_file), "no designData.json in the batches folder")
        self.assertEqual(json.loads(read_text(design_file)), {"a": "live a", "b": "live b", "c": "copy c"},
                         "the live designData must win a shared key, and the copy's new key must be added")

    def test_copy_designs_without_a_live_page_are_unknown_and_write_nothing(self):
        live = self.fetch(items={"item-001": item(1)})
        copy = self.copy_with_designs({"items": {"item-002": item(2)}}, {"c": "copy c"})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertNoBatches(batches, "a copy with designs and no --live-page")
        self.assertFalse(os.path.exists(os.path.join(batches, "designData.json")), "designData.json was written")

    def test_a_copy_without_designs_needs_no_live_page_and_reports_zero_designs(self):
        live = self.fetch(items={"item-001": item(1)})
        copy = self.copy_of({"items": {"item-002": item(2)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 1, 0, 0, designs=0)

    def test_a_live_page_with_no_designdata_block_is_unknown_when_the_copy_has_designs(self):
        live = self.fetch(items={"item-001": item(1)})
        live_page = write_bytes(os.path.join(self.tmp.name, "queue.html"), QUEUE_PAGE)
        copy = self.copy_with_designs({"items": {"item-002": item(2)}}, {"c": "copy c"})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches, live_page=live_page)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertNoBatches(batches, "a live page with no designData block")

    def test_merge_writes_the_renumber_map_from_each_old_n_to_its_new_n(self):
        live = self.fetch(items={"item-001": item(1), "item-002": item(2), "item-003": item(3)})
        copy = self.copy_with_a_clash()
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 2, 3, 1)
        renumbered = os.path.join(batches, "renumbered.json")
        self.assertTrue(os.path.isfile(renumbered), "no renumbered.json in the batches folder")
        self.assertEqual(json.loads(read_text(renumbered)), {"2": 4},
                         "item-900 moved from n 2 to n 4: the map must read {\"2\": 4}, with string keys")

    def test_the_renumber_map_is_written_empty_when_no_n_moves(self):
        live = self.fetch(items={"item-009": item(9)})
        copy = self.copy_of({"items": {"item-001": item(1), "item-002": item(2)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 2, 0, 0)
        renumbered = os.path.join(batches, "renumbered.json")
        self.assertTrue(os.path.isfile(renumbered), "renumbered.json is not written when no n moves: it must be, empty")
        self.assertEqual(json.loads(read_text(renumbered)), {}, "the map of a merge with no moves must be {}")

    def test_the_renumber_map_keys_only_the_item_that_moved_when_two_copies_share_an_n(self):
        # item-a keeps 7 (no live clash). item-b, the later one, takes 8. The map keys item-b's old n and no other item.
        copy = self.copy_of({"items": {"item-a": item_as("item-a", 7), "item-b": item_as("item-b", 7)}})
        live = self.fetch()
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 2, 0, 1)
        renumbered = os.path.join(batches, "renumbered.json")
        self.assertTrue(os.path.isfile(renumbered), "no renumbered.json in the batches folder")
        self.assertEqual(json.loads(read_text(renumbered)), {"7": 8},
                         "only the mover is keyed, and its key maps to its own new n 8: the keeper must not appear")

    def test_the_design_file_holds_no_raw_less_than_and_parses_to_the_same_values(self):
        # The file is pasted into the page's script block as it is, so a "</script>" in a value must not reach it raw.
        live = self.fetch(items={"item-001": item(1)})
        live_page = self.live_page_with({"a": "live </script> a"})
        copy = self.copy_with_designs({"items": {"item-002": item(2)}}, {"c": "copy <b>tag</b>"})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches, live_page=live_page)
        self.assertMergeSummary(r, 1, 1, 0, 0, designs=1)
        design_file = os.path.join(batches, "designData.json")
        self.assertTrue(os.path.isfile(design_file), "no designData.json in the batches folder")
        raw = read_text(design_file)
        self.assertNotIn("<", raw, "designData.json holds a raw '<': every '<' must be written as the escape \\u003c")
        ESCAPE = chr(92) + "u003c"  # the six characters of the JSON escape for '<'
        self.assertIn(ESCAPE, raw, "designData.json has no escape for the '<' in its values")
        self.assertEqual(json.loads(raw), {"a": "live </script> a", "c": "copy <b>tag</b>"},
                         "designData.json must parse to the live values plus the copy's added key")

    def test_fifty_one_missing_docs_with_one_live_make_one_batch_of_fifty(self):
        live = self.fetch(items={"item-001": item(1)})
        copy = self.copy_of({"items": {"item-%03d" % n: item(n) for n in range(1, 52)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 50, 1, 0)
        _, entries, sizes = self.batch_entries(batches)
        self.assertEqual(sizes, [50], "one batch of 50 entries, not %s" % sizes)
        self.assertEqual(sorted(e["doc_id"] for e in entries), sorted("item-%03d" % n for n in range(2, 52)),
                         "the batch does not hold the 50 docs the live page lacks")

    def test_merge_batches_stay_under_900_kb(self):
        # 100 docs of about 20 KB: the byte cap splits them, as it does for --rebuild.
        big = {"item-%03d" % n: dict(item(n), context="word " * 4000) for n in range(1, 101)}
        copy = self.copy_of({"items": big})
        live = self.fetch()
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        files = self.batch_files(batches)
        self.assertMergeSummary(r, len(files), 100, 0, 0)
        self.assertGreaterEqual(len(files), 3, "2 MB of docs cannot fit in fewer than three 900 KB batches")
        for path in files:
            self.assertLessEqual(os.path.getsize(path), 900000, "%s is over 900 KB" % os.path.basename(path))
        _, entries, _ = self.batch_entries(batches)
        self.assertEqual(len(entries), 100, "the batches hold %d entries, not 100" % len(entries))

    def test_a_doc_over_900_kb_is_unknown_for_a_merge(self):
        copy = self.copy_of({"items": {"item-001": dict(item(1), context="word " * 200000)}})
        live = self.fetch()
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertVerdict(r, "unknown")
        self.assertEqual(r.returncode, 2, shown(r))
        self.assertNoBatches(batches, "a doc over the byte cap")

    def test_a_copied_item_with_a_live_n_takes_the_next_free_n_and_its_answer_follows(self):
        live = self.fetch(items={"item-001": item(1), "item-002": item(2), "item-003": item(3)})
        copy = self.copy_with_a_clash()
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 2, 3, 1)
        _, entries, _ = self.batch_entries(batches)
        moved = self.entry_of(entries, "items", "item-900")
        answer = self.entry_of(entries, "answers", "item-900")
        self.assertIsNotNone(moved, "items/item-900 is not in the batches")
        self.assertIsNotNone(answer, "answers/item-900 is not in the batches: its item was renumbered, so its answer follows")
        self.assertEqual(moved["data"].get("n"), 4, "items/item-900 has n %s, not the next free n above 3, which is 4"
                         % moved["data"].get("n"))
        self.assertEqual(answer["data"].get("n"), 4, "answers/item-900 has n %s, not its item's new n 4"
                         % answer["data"].get("n"))
        self.assertEqual(self.unnumbered(moved["data"]), self.unnumbered(item_as("item-900", 2)),
                         "items/item-900 changed a field other than n")
        self.assertEqual(self.unnumbered(answer["data"]), self.unnumbered(answer_for("item-900", 2)),
                         "answers/item-900 changed a field other than n")

    def test_a_renumbered_answer_names_its_item_by_the_doc_key_not_by_the_id_field(self):
        live = self.fetch(items={"item-001": item(1), "item-002": item(2), "item-003": item(3)})
        copy = self.copy_with_a_clash(id_field="other-id")
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 2, 3, 1)
        _, entries, _ = self.batch_entries(batches)
        moved = self.entry_of(entries, "items", "item-900")
        self.assertIsNotNone(moved, "items/item-900 is not in the batches: the clash did not renumber it")
        self.assertEqual(moved["data"].get("n"), 4, "items/item-900 has n %s, not the next free n 4" % moved["data"].get("n"))
        answer = self.entry_of(entries, "answers", "item-900")
        self.assertIsNotNone(answer, "answers/item-900 is not in the batches: its item was renumbered, so its answer follows")
        self.assertEqual(answer["data"].get("item"), "item-900",
                         "answers/item-900 names item %r, not its doc key item-900" % answer["data"].get("item"))

    def test_copied_items_that_share_an_n_renumber_the_later_one_and_its_answer(self):
        live = self.fetch()
        copy = self.copy_of({
            "items": {"item-a": item_as("item-a", 7), "item-b": item_as("item-b", 7)},
            "answers": {"item-a": answer_for("item-a", 7), "item-b": answer_for("item-b", 7)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 4, 0, 1)
        _, entries, _ = self.batch_entries(batches)
        got = {(e["collection"], e["doc_id"]): e["data"].get("n") for e in entries}
        self.assertEqual(got, {("items", "item-a"): 7, ("items", "item-b"): 8,
                               ("answers", "item-a"): 7, ("answers", "item-b"): 8},
                         "of two copied items with n 7, the earlier (sorted doc_id) keeps 7, and the later takes 8 with its answer")

    def test_a_new_n_is_above_the_highest_n_in_either_folder(self):
        # Live holds n 1 to 3. Copy's item-a clashes with live item-002, and copy's item-b holds 4. A new n of 4 would
        # clash with item-b, so item-a takes 5: the next free n above the highest in either folder.
        live = self.fetch(items={"item-001": item(1), "item-002": item(2), "item-003": item(3)})
        copy = self.copy_of({"items": {"item-001": item(1), "item-002": item(2), "item-003": item(3),
                                       "item-a": item_as("item-a", 2), "item-b": item_as("item-b", 4)}})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches)
        self.assertMergeSummary(r, 1, 2, 3, 1)
        _, entries, _ = self.batch_entries(batches)
        got = {e["doc_id"]: e["data"].get("n") for e in entries if e["collection"] == "items"}
        self.assertEqual(got, {"item-a": 5, "item-b": 4},
                         "item-a's n 2 is held live: the next free n above the highest in either folder is 5, and item-b keeps 4")

    def test_merge_with_collections_writes_each_named_folder_under_its_name(self):
        steps = {"step-%03d" % n: {"n": n, "title": "Step %d" % n} for n in range(1, 31)}
        topics = {"topic-%03d" % n: {"n": n, "title": "Topic %d" % n} for n in range(1, 31)}
        # `receipts` is named in the live page and absent from the copy: the copy holds none of it, which is fine.
        live = self.fetch(folders={"steps": {"step-001": steps["step-001"]}, "topics": {}, "receipts": {}})
        copy = self.copy_of({"steps": steps, "topics": topics})
        batches = os.path.join(self.tmp.name, "batches")
        r = self.merge_run(copy, live, batches, collections=("steps", "topics", "receipts"))
        self.assertMergeSummary(r, 2, 59, 1, 0)
        _, entries, _ = self.batch_entries(batches)
        want = collections.Counter(
            [("steps", doc_id, canonical(doc)) for doc_id, doc in steps.items() if doc_id != "step-001"]
            + [("topics", doc_id, canonical(doc)) for doc_id, doc in topics.items()])
        got = collections.Counter((e["collection"], e["doc_id"], canonical(e["data"])) for e in entries)
        self.assertEqual(got, want, "the batches do not hold the named folders' missing docs under their folder names")

    def test_merge_with_collections_names_a_folder_not_named_as_unknown(self):
        forms = {
            "copy": (self.copy_of({"steps": {"step-001": {"n": 1}}, "items": {"item-001": item(1)}}),
                     self.fetch(folders={"steps": {}, "topics": {}})),
            "live": (self.copy_of({"steps": {"step-001": {"n": 1}}}),
                     self.fetch(folders={"steps": {}, "topics": {}, "items": {"item-001": item(1)}})),
        }
        for label, (copy, live) in forms.items():
            batches = os.path.join(self.tmp.name, "batches-" + label)
            with self.subTest(form=label):
                r = self.merge_run(copy, live, batches, collections=("steps", "topics"))
                lines = [line for line in verdict_lines(r) if line.startswith("unknown")]
                self.assertTrue(any("items" in line for line in lines),
                                "no unknown line names items in the %s. Output:\n%s" % (label, shown(r)))
                self.assertEqual(r.returncode, 2, shown(r))
                self.assertNoBatches(batches, "an unnamed folder in the " + label)

    def test_merge_collections_follow_the_rebuild_name_rules(self):
        copy = self.copy_of({"steps": {"step-001": {"n": 1}}})
        live = self.fetch(folders={"steps": {}})
        for number, bad in enumerate(("page", "../steps")):
            batches = os.path.join(self.tmp.name, "batches-%d" % number)
            with self.subTest(name=bad):
                r = self.merge_run(copy, live, batches, collections=(bad,))
                err = error_line(r)
                self.assertIsNotNone(err, "no usage error line for %r. Output:\n%s" % (bad, shown(r)))
                self.assertNotIn("unrecognized arguments", err,
                                 "argparse rejected the command before the name %r was checked: %s" % (bad, err))
                self.assertIn(bad, err, "the usage error does not name %r: %s" % (bad, err))
                self.assertEqual(r.returncode, 2, shown(r))
                self.assertNoBatches(batches, "a usage error")

    def test_a_control_rebuilds_the_clash_copy_so_its_fixture_is_well_formed(self):
        """Green on the old code: the copy the renumber case merges also rebuilds, so a red there is the merge."""
        copy = self.copy_with_a_clash(name="control")
        batches = os.path.join(self.tmp.name, "batches")
        r = self.rebuild(copy, batches)
        self.assertBatches(r, 1, 5)


class All(Base):
    """--all: each artifact in the repo's registry (the "artifacts" key of its extras file) exports its collections to
    its export path under --worktree: the waiting page to waiting/, any other artifact to artifacts/<id>/. Each artifact
    gets the same scan and mirror as a single export, and one verdict line of its own, named by its id."""
    WAIT, QUEUE = "page01", "queue02"
    VERDICT = r"\b(changed\s+\d+|same|refused|unknown)\b"

    def queue_entry(self, **changes):
        return dict({"id": self.QUEUE, "url": "https://claude.ai/artifact/" + self.QUEUE, "role": "queue-page", "account": "work",
                     "collections": ["items"]}, **changes)

    def repo(self, queue=None, mark=None):
        """The registry: the waiting page, then the queue entry. `queue` replaces the queue entry for a case of another shape.
        `mark` sets the extras file's "rolled-out" value when given, such as a bad mark."""
        root = os.path.join(self.tmp.name, "repo")
        registry = {"kinds": {}, "artifacts": [
            {"id": self.WAIT, "url": "https://claude.ai/artifact/" + self.WAIT, "role": "waiting-page", "account": "work"},
            queue or self.queue_entry()]}
        if mark is not None:
            registry["rolled-out"] = mark
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps(registry))
        return root

    def docs(self):
        """What each artifact's fetch holds. The queue lists items only, so its answers are fetched but never exported."""
        return {self.WAIT: dict(items={"i1": item(1)}, answers={"a1": {"item": "i1", "pick": "a"}},
                                groups={"g1": {"name": "Group"}}, asks={"k1": {"item": "i1"}}, meta={"page": META}),
                self.QUEUE: dict(items={"q1": item(2)}, answers={"qa1": {"item": "q1", "pick": "b"}})}

    def fetched_all(self, docs, pages=None, files=None):
        """One fetched folder per artifact id, each shaped as a single fetch is. `pages` maps an id to its page.html
        bytes; `files` maps an id to {path under files/: bytes}, the page's supporting files. An id whose `docs` value is
        None is a page-only fetch: its folder holds the page and files and no collection folder."""
        root = tempfile.mkdtemp(prefix="fetched-all-", dir=self.tmp.name)
        for artifact_id, parts in docs.items():
            folder = self.fetch(**parts) if parts is not None else tempfile.mkdtemp(prefix="fetched-page-", dir=self.tmp.name)
            if pages and artifact_id in pages:
                write_bytes(os.path.join(folder, "page.html"), pages[artifact_id])
            for rel, data in ((files or {}).get(artifact_id) or {}).items():
                write_bytes(os.path.join(folder, "files", *rel.split("/")), data)
            os.rename(folder, os.path.join(root, artifact_id))
        return root

    def export_folder(self, worktree, artifact_id):
        """Where an artifact's export lands: the waiting page's `waiting/`, any other artifact's `artifacts/<id>/`."""
        return os.path.join(worktree, "waiting") if artifact_id == self.WAIT else os.path.join(worktree, "artifacts", artifact_id)

    def run_all(self, root, fetched, worktree):
        r = self.run_cmd("--all", root, "--fetched", fetched, "--worktree", worktree)
        if r.returncode == 2 and "unrecognized arguments" in r.stderr:
            self.fail("export_page.py has no --all mode: argparse refused it. Output:\n" + shown(r))
        return r

    def verdict_of(self, r, artifact_id):
        """The one verdict line of an artifact: a line that names its id and carries a verdict word."""
        found = [line for line in verdict_lines(r) if artifact_id in line and re.search(self.VERDICT, line)]
        self.assertEqual(len(found), 1, "%s needs one verdict line, found %d. Output:\n%s" % (artifact_id, len(found), shown(r)))
        return found[0]

    def assertVerdictOf(self, r, artifact_id, word):
        line = self.verdict_of(r, artifact_id)
        self.assertTrue(re.search(word, line), "%s: its verdict line is not %r: %r. Output:\n%s" % (artifact_id, word, line, shown(r)))

    def test_each_artifact_exports_its_collections_to_its_export_path(self):
        worktree = self.out("worktree")
        r = self.run_all(self.repo(), self.fetched_all(self.docs()), worktree)
        self.assertEqual(r.returncode, 0, shown(r))
        waiting = self.export_folder(worktree, self.WAIT)
        for name in COLLECTIONS:
            self.assertTrue(os.path.isdir(os.path.join(waiting, name)), "the waiting page did not export its %s/ collection" % name)
        self.assertEqual(read_text(os.path.join(waiting, "items", "i1.json")), canonical(item(1)), "the waiting page's item did not land")
        self.assertEqual(read_text(os.path.join(waiting, "meta", "page.json")), canonical(META), "the waiting page's meta did not land")
        queue = self.export_folder(worktree, self.QUEUE)
        self.assertEqual(read_text(os.path.join(queue, "items", "q1.json")), canonical(item(2)), "the queue's item did not land")
        self.assertFalse(os.path.exists(os.path.join(queue, "answers")), "an artifact exported a collection its entry does not list")

    def test_a_bad_rolled_out_mark_still_exports_the_page_to_waiting(self):
        """A "rolled-out" that is not JSON true or false: the export reads the waiting folder under either mark, so the
        waiting page still exports to waiting/ and the queue to artifacts/<id>/. The valid mark is the control."""
        for label, mark in (("valid", True), ("bad", "yes")):
            with self.subTest(mark=label):
                worktree = self.out("worktree-%s" % label)
                r = self.run_all(self.repo(mark=mark), self.fetched_all(self.docs()), worktree)
                self.assertEqual(r.returncode, 0, shown(r))
                self.assertVerdictOf(r, self.WAIT, r"changed\s+5\b")  # five docs, one per collection
                waiting = self.export_folder(worktree, self.WAIT)
                self.assertEqual(read_text(os.path.join(waiting, "items", "i1.json")), canonical(item(1)),
                                 "under a %s mark the waiting page's item did not land in waiting/" % label)
                queue = self.export_folder(worktree, self.QUEUE)
                self.assertEqual(read_text(os.path.join(queue, "items", "q1.json")), canonical(item(2)),
                                 "under a %s mark the queue's item did not land in artifacts/" % label)

    def test_each_artifact_gets_one_verdict_line_with_its_verdict(self):
        root, fetched, worktree = self.repo(), self.fetched_all(self.docs()), self.out("worktree")
        first = self.run_all(root, fetched, worktree)
        self.assertEqual(first.returncode, 0, shown(first))
        self.assertVerdictOf(first, self.WAIT, r"changed\s+5\b")  # five docs, one per collection
        self.assertVerdictOf(first, self.QUEUE, r"changed\s+1\b")  # one item; the answers are not exported
        second = self.run_all(root, fetched, worktree)
        self.assertEqual(second.returncode, 0, shown(second))
        self.assertVerdictOf(second, self.WAIT, r"\bsame\b")
        self.assertVerdictOf(second, self.QUEUE, r"\bsame\b")

    def test_an_artifact_with_no_docs_exports_nothing_and_reports_same(self):
        docs = self.docs()
        docs[self.QUEUE] = dict(items={}, answers={})  # the empty state a new page starts in
        worktree = self.out("worktree")
        r = self.run_all(self.repo(), self.fetched_all(docs), worktree)
        self.assertEqual(r.returncode, 0, shown(r))
        self.assertVerdictOf(r, self.QUEUE, r"\bsame\b")
        found = glob.glob(os.path.join(self.export_folder(worktree, self.QUEUE), "**", "*.json"), recursive=True)
        self.assertEqual(found, [], "an artifact with no docs exported files")

    def test_a_find_refuses_only_its_artifact_and_the_run_exits_1(self):
        for leaky, clean in ((self.WAIT, self.QUEUE), (self.QUEUE, self.WAIT)):
            with self.subTest(leaky=leaky):
                root, worktree = self.repo(), self.out("worktree-" + leaky)
                self.assertEqual(self.run_all(root, self.fetched_all(self.docs()), worktree).returncode, 0, "the clean first run failed")
                before = snapshot(self.export_folder(worktree, leaky))
                docs = self.docs()
                docs[leaky]["items"]["leak"] = dict(item(9), note="ghp_" + TAIL)
                docs[clean]["items"]["fresh"] = item(10)
                r = self.run_all(root, self.fetched_all(docs), worktree)
                self.assertEqual(r.returncode, 1, "a find in one artifact must exit 1. Output:\n" + shown(r, [TAIL]))
                self.assertNotIn(TAIL, r.stdout + r.stderr, "the matched value was printed")
                self.assertVerdictOf(r, leaky, r"\brefused\b")
                self.assertVerdictOf(r, clean, r"changed\s+1\b")
                self.assertEqual(snapshot(self.export_folder(worktree, leaky)), before, "a refused artifact changed its copy")
                self.assertTrue(os.path.isfile(os.path.join(self.export_folder(worktree, clean), "items", "fresh.json")),
                                "the clean artifact was held back by the refused one")

    def test_each_artifact_page_html_lands_under_its_export_path(self):
        pages = {self.WAIT: PAGE_BYTES, self.QUEUE: QUEUE_PAGE}  # the waiting page, and a page of another role
        worktree = self.out("worktree")
        r = self.run_all(self.repo(), self.fetched_all(self.docs(), pages=pages), worktree)
        self.assertEqual(r.returncode, 0, shown(r))
        for artifact_id, want in pages.items():
            with self.subTest(artifact=artifact_id):
                self.verdict_of(r, artifact_id)  # the scope: the artifact's own verdict line
                landed = os.path.join(self.export_folder(worktree, artifact_id), "page", "page.html")
                self.assertTrue(os.path.isfile(landed), "%s: page/page.html was not exported. Output:\n%s" % (artifact_id, shown(r)))
                self.assertEqual(read_bytes(landed), want, "%s: page/page.html is not byte-identical" % artifact_id)

    def test_supporting_files_land_under_the_page_folder_of_their_artifact(self):
        files = {self.QUEUE: {"assets/app.js": b'console.log("ready");\n', "img/mark.bin": b"\x00\x01\xfe\xff"}}
        worktree = self.out("worktree")
        r = self.run_all(self.repo(), self.fetched_all(self.docs(), pages={self.QUEUE: QUEUE_PAGE}, files=files), worktree)
        self.assertEqual(r.returncode, 0, shown(r))
        self.verdict_of(r, self.QUEUE)  # the scope: the artifact's own verdict line
        base = os.path.join(self.export_folder(worktree, self.QUEUE), "page", "files")
        for rel, want in files[self.QUEUE].items():
            with self.subTest(file=rel):
                landed = os.path.join(base, *rel.split("/"))
                self.assertTrue(os.path.isfile(landed), "%s was not exported under page/files/. Output:\n%s" % (rel, shown(r)))
                self.assertEqual(read_bytes(landed), want, "%s is not byte-identical" % rel)
        self.assertVerdictOf(r, self.QUEUE, r"changed\s+4\b")  # one item, the page, and the two files: one count per file

    def test_an_artifact_with_no_docs_still_exports_its_page(self):
        docs = self.docs()
        docs[self.QUEUE] = dict(items={}, answers={})  # the empty state of a new page, with its page already made
        worktree = self.out("worktree")
        r = self.run_all(self.repo(), self.fetched_all(docs, pages={self.QUEUE: QUEUE_PAGE}), worktree)
        self.assertEqual(r.returncode, 0, shown(r))
        self.verdict_of(r, self.QUEUE)  # the scope: the artifact's own verdict line
        landed = os.path.join(self.export_folder(worktree, self.QUEUE), "page", "page.html")
        self.assertTrue(os.path.isfile(landed), "the empty artifact's page/page.html was not exported. Output:\n" + shown(r))
        self.assertEqual(read_bytes(landed), QUEUE_PAGE, "the empty artifact's page/page.html is not byte-identical")
        self.assertVerdictOf(r, self.QUEUE, r"changed\s+1\b")

    def test_a_page_only_entry_of_the_flag_account_exports_its_page_and_file_then_reports_same(self):
        """--all --account other, with a page-only entry (`collections` []) whose fetch holds page.html and files/x.js: both
        export under artifacts/<id>/page/ and the run prints `changed 2`, exit 0. A second run prints `same`."""
        script = b'console.log("page only");\n'
        page_only = self.queue_entry(account="other", collections=[])
        fetched = self.fetched_all({self.QUEUE: None}, pages={self.QUEUE: QUEUE_PAGE}, files={self.QUEUE: {"x.js": script}})
        root, worktree = self.repo(queue=page_only), self.out("worktree")
        args = ("--all", root, "--fetched", fetched, "--worktree", worktree, "--account", "other")
        first = self.run_cmd(*args)
        self.assertEqual(first.returncode, 0,
                         "a page-only entry of the flag's account was not exported. Output:\n" + shown(first))
        self.assertVerdictOf(first, self.QUEUE, r"changed\s+2\b")
        base = os.path.join(self.export_folder(worktree, self.QUEUE), "page")
        self.assertEqual(read_bytes(os.path.join(base, "page.html")), QUEUE_PAGE, "page/page.html is not byte-identical")
        self.assertEqual(read_bytes(os.path.join(base, "files", "x.js")), script, "page/files/x.js is not byte-identical")
        self.assertIn("%s: skipped - account work" % self.WAIT, verdict_lines(first),
                      "the waiting page of another account was not skipped")
        second = self.run_cmd(*args)
        self.assertEqual(second.returncode, 0, "the second run of a page-only entry failed. Output:\n" + shown(second))
        self.assertVerdictOf(second, self.QUEUE, r"\bsame\b")

    def test_a_page_only_entry_with_no_page_html_is_unknown_and_writes_nothing(self):
        """--all --account work, with a page-only entry (`collections` []) whose fetched folder exists and holds no page.html:
        its line is `<id>: unknown - ...` naming page.html, nothing lands under its export path, and the run exits 2."""
        fetched = self.fetched_all({self.WAIT: self.docs()[self.WAIT], self.QUEUE: None})  # the queue's folder: no page.html
        root, worktree = self.repo(queue=self.queue_entry(collections=[])), self.out("worktree")
        r = self.run_cmd("--all", root, "--fetched", fetched, "--worktree", worktree, "--account", "work")
        line = self.verdict_of(r, self.QUEUE)  # the scope: the page-only artifact's own verdict line
        self.assertTrue(line.startswith(self.QUEUE + ": unknown - "),
                        "a page-only entry whose folder has no page.html is not unknown: %r. Output:\n%s" % (line, shown(r)))
        self.assertIn("page.html", line, "the unknown line does not name the missing page.html: %r" % line)
        self.assertEqual(r.returncode, 2, "an unknown artifact must make the run exit 2. Output:\n" + shown(r))
        self.assertFalse(os.path.exists(self.export_folder(worktree, self.QUEUE)),
                         "the page-only entry wrote into its export path although its page is missing")

    def test_a_page_only_entry_with_page_html_still_exports_its_page_and_exits_0(self):
        """Control beside the case above: the same page-only entry with its page.html exports as today, `changed 1`, exit 0."""
        fetched = self.fetched_all({self.WAIT: self.docs()[self.WAIT], self.QUEUE: None}, pages={self.QUEUE: QUEUE_PAGE})
        root, worktree = self.repo(queue=self.queue_entry(collections=[])), self.out("worktree")
        r = self.run_cmd("--all", root, "--fetched", fetched, "--worktree", worktree, "--account", "work")
        self.assertEqual(r.returncode, 0, "a page-only entry with its page.html must exit 0. Output:\n" + shown(r))
        self.assertVerdictOf(r, self.QUEUE, r"changed\s+1\b")
        landed = os.path.join(self.export_folder(worktree, self.QUEUE), "page", "page.html")
        self.assertTrue(os.path.isfile(landed), "page/page.html was not exported for the page-only entry. Output:\n" + shown(r))
        self.assertEqual(read_bytes(landed), QUEUE_PAGE, "the page-only entry's page/page.html is not byte-identical")

    def test_a_secret_in_an_artifacts_page_refuses_only_that_artifact(self):
        root, worktree = self.repo(), self.out("worktree")
        pages = {self.WAIT: PAGE_BYTES, self.QUEUE: QUEUE_PAGE}
        self.assertEqual(self.run_all(root, self.fetched_all(self.docs(), pages=pages), worktree).returncode, 0,
                         "the clean first run failed")
        before = snapshot(self.export_folder(worktree, self.QUEUE))
        leaky = QUEUE_PAGE + ("<p>Token: %s</p>\r\n" % TOKEN).encode("utf-8")
        docs = self.docs()
        docs[self.WAIT]["items"]["fresh"] = item(10)  # the clean artifact has a new doc, so it must still export
        held = dict(pages)
        held[self.QUEUE] = leaky
        r = self.run_all(root, self.fetched_all(docs, pages=held), worktree)
        self.assertVerdictOf(r, self.QUEUE, r"\brefused\b")
        self.assertEqual(r.returncode, 1, "a find in one artifact's page must exit 1. Output:\n" + shown(r, [TOKEN]))
        self.assertNotIn(TOKEN, r.stdout + r.stderr, "the matched value was printed")
        self.assertEqual(snapshot(self.export_folder(worktree, self.QUEUE)), before, "a refused page changed its artifact's copy")
        self.assertVerdictOf(r, self.WAIT, r"changed\s+1\b")
        self.assertTrue(os.path.isfile(os.path.join(self.export_folder(worktree, self.WAIT), "items", "fresh.json")),
                        "the clean artifact was held back by the refused page")

    def assert_supporting_file_refused(self, label, rel, data, secrets):
        """A clean run first. Then a run whose QUEUE supporting file is `rel` with `data`: QUEUE is refused, exits 1,
        prints no secret and changes nothing; WAIT still exports its new doc."""
        root, worktree = self.repo(), self.out("worktree-" + label)
        pages = {self.WAIT: PAGE_BYTES, self.QUEUE: QUEUE_PAGE}
        clean = self.run_all(root, self.fetched_all(self.docs(), pages=pages), worktree)
        self.assertEqual(clean.returncode, 0, "%s: the clean first run failed. Output:\n%s" % (label, shown(clean)))
        before = snapshot(self.export_folder(worktree, self.QUEUE))
        docs = self.docs()
        docs[self.WAIT]["items"]["fresh"] = item(10)  # the clean artifact has a new doc, so it must still export
        r = self.run_all(root, self.fetched_all(docs, pages=pages, files={self.QUEUE: {rel: data}}), worktree)
        self.assertVerdictOf(r, self.QUEUE, r"\brefused\b")
        self.assertEqual(r.returncode, 1, "%s: a find in a supporting file must exit 1. Output:\n%s" % (label, shown(r, secrets)))
        for secret in secrets:
            self.assertNotIn(secret, r.stdout + r.stderr, "%s: the matched value was printed" % label)
        self.assertEqual(snapshot(self.export_folder(worktree, self.QUEUE)), before, "%s: a refused artifact changed its copy" % label)
        self.assertVerdictOf(r, self.WAIT, r"changed\s+1\b")

    def test_a_token_or_email_in_a_supporting_text_file_refuses_that_artifact(self):
        cases = (("token-text", b"token: " + TOKEN.encode("ascii"), [TOKEN]),
                 ("email-text", b"mail: " + MAIL.encode("ascii"), [MAIL]))
        for label, data, secrets in cases:
            with self.subTest(label=label):
                self.assert_supporting_file_refused(label, "notes.txt", data, secrets)

    def test_a_token_or_email_in_a_supporting_file_name_refuses_that_artifact(self):
        cases = (("token-name", "assets/" + TOKEN + ".txt", [TOKEN]),
                 ("email-name", "assets/" + MAIL + ".txt", [MAIL]))
        for label, rel, secrets in cases:
            with self.subTest(label=label):
                self.assert_supporting_file_refused(label, rel, b"fine\n", secrets)

    def test_a_cp1252_supporting_text_file_with_an_email_refuses_that_artifact(self):
        self.assert_supporting_file_refused("cp1252-email", "notes/cafe.txt", b"caf\xe9 " + MAIL.encode("ascii"), [MAIL])

    def test_url_credentials_on_an_ip_host_in_a_supporting_text_file_refuse_that_artifact(self):
        self.assert_supporting_file_refused("ip-url", "notes/db.txt", ("Database: %s\n" % DB_IP_URL).encode("ascii"), [PASSWORD])

    def test_a_text_file_under_an_image_or_font_name_is_scanned(self):
        cases = (("font-password", "fonts/x.woff", ("password = " + PASSWORD).encode("ascii"), [PASSWORD]),
                 ("image-email", "img/logo.png", ("Contact " + MAIL + "\n").encode("ascii"), [MAIL]))
        for label, rel, data, secrets in cases:
            with self.subTest(label=label):
                self.assert_supporting_file_refused(label, rel, data, secrets)

    def test_a_real_binary_under_an_image_or_font_name_exports_unscanned(self):
        """The control for the case above: a file with a NUL byte is binary, whatever its name. Its bytes are not scanned,
        so email- and password-shaped bytes in it still export."""
        cases = (("png", "img/photo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR " + MAIL.encode("ascii")),
                 ("woff", "fonts/real.woff", b"wOFF\x00\x01\x00\x00password = " + PASSWORD.encode("ascii")))
        for label, rel, data in cases:
            with self.subTest(label=label):
                worktree = self.out("worktree-" + label)
                files = {self.QUEUE: {rel: data}}
                r = self.run_all(self.repo(), self.fetched_all(self.docs(), pages={self.QUEUE: QUEUE_PAGE}, files=files), worktree)
                self.verdict_of(r, self.QUEUE)  # the scope: the artifact's own verdict line
                self.assertEqual(r.returncode, 0, "%s: a real binary was refused. Output:\n%s" % (label, shown(r)))
                landed = os.path.join(self.export_folder(worktree, self.QUEUE), "page", "files", *rel.split("/"))
                self.assertTrue(os.path.isfile(landed), "%s was not exported under page/files/. Output:\n%s" % (rel, shown(r)))
                self.assertEqual(read_bytes(landed), data, "%s is not byte-identical" % rel)
                self.assertVerdictOf(r, self.QUEUE, r"changed\s+3\b")  # one item, the page, and the file

    def test_a_retina_file_name_is_not_an_email(self):
        png = b"\x89PNG\r\n\x1a\n"  # not UTF-8, so it is read as latin-1 and scanned; no shape is in these bytes, only in the name
        worktree = self.out("worktree")
        files = {self.QUEUE: {"img/logo@2x.png": png}}
        r = self.run_all(self.repo(), self.fetched_all(self.docs(), pages={self.QUEUE: QUEUE_PAGE}, files=files), worktree)
        self.assertEqual(r.returncode, 0, "img/logo@2x.png was refused as an email. Output:\n" + shown(r))
        self.verdict_of(r, self.QUEUE)  # the scope: the artifact's own verdict line
        landed = os.path.join(self.export_folder(worktree, self.QUEUE), "page", "files", "img", "logo@2x.png")
        self.assertTrue(os.path.isfile(landed), "img/logo@2x.png was not exported under page/files/. Output:\n" + shown(r))
        self.assertEqual(read_bytes(landed), png, "img/logo@2x.png is not byte-identical")
        self.assertVerdictOf(r, self.QUEUE, r"changed\s+3\b")  # one item, the page, and the file

    def test_the_switch_steps_out_dir_fetch_exports_each_artifact_changed(self):
        # Step 2 of "Before you switch Claude accounts" names out_dir and the marker's path in backticks. ArtifactData
        # writes each doc to <out_dir>/<collection>/<doc_id>.json. The marker is touched where the step names it, and an
        # empty collection gets a folder only where the step says to make one by hand. The text is read from the skill's
        # files (SKILL.md and reference/*.md), never copied here, so a change to that step is what this case checks.
        step2 = skill_step("## Before you switch Claude accounts", 2)
        found = re.search(r"`out_dir`\s+(?:set\s+to|=)\s*`([^`]+)`", step2)
        self.assertTrue(found, "step 2 names no out_dir path, so the fetch layout cannot be read from the skill")
        template = found.group(1)
        self.assertTrue("<folder>" in template and "<id>" in template,
                        "step 2's out_dir %r lacks <folder> or <id>" % template)
        marked = re.search(r"`([^`]*/\.complete)`", step2)
        self.assertTrue(marked, "step 2 names no backticked path ending in /.complete, so the marker's place cannot be read")
        marker = marked.group(1)
        by_hand = re.search(r"\bmake\b[^.]*\bby\s+hand\b", step2, re.I)

        def place(text, artifact_id, collection):
            names = {"folder": fetched, "id": artifact_id, "collection": collection}
            return re.sub(r"<(folder|id|collection)>", lambda m: names[m.group(1)], text)

        root = self.repo()
        registry = json.loads(read_text(os.path.join(root, ".claude", "layout-extras.json")))["artifacts"]
        pages = {self.WAIT: PAGE_BYTES, self.QUEUE: QUEUE_PAGE}
        docs = self.docs()
        docs[self.WAIT]["groups"] = {}  # an empty collection: the tool writes no file for it
        fetched = os.path.join(self.tmp.name, "switch")
        for entry in registry:
            artifact_id = entry["id"]
            for collection in entry.get("collections", COLLECTIONS):
                out_dir = place(template, artifact_id, collection)
                for doc_id, data in (docs[artifact_id].get(collection) or {}).items():
                    write_text(os.path.join(out_dir, collection, doc_id + ".json"), canonical(data))
                folder = os.path.dirname(place(marker, artifact_id, collection))
                if by_hand and not os.path.isdir(folder):
                    os.makedirs(folder)  # the step makes the folder of a collection the tool wrote nothing to
                if os.path.isdir(folder):
                    write_text(place(marker, artifact_id, collection), "")  # touch: a missing folder cannot be touched
            write_bytes(os.path.join(fetched, artifact_id, "page.html"), pages[artifact_id])

        worktree = self.out("worktree")
        r = self.run_all(root, fetched, worktree)
        for entry in registry:
            artifact_id = entry["id"]
            line = self.verdict_of(r, artifact_id)  # the scope: the artifact's own verdict line
            self.assertRegex(line, r"changed\s+\d+",
                             "%s: not changed after the switch step's out_dir %r and marker %r. Its line:\n%s"
                             % (artifact_id, template, marker, line))
        self.assertEqual(r.returncode, 0, shown(r))


class NoExport(Base):
    """`"export": false` (decision waiting-data-in-repo): an artifact the repo holds and does not export, such as a page in
    an account this session cannot read. `--all` prints `<id>: skipped - no export` for it, exits 0 for it and needs no
    fetched folder for it. The other artifacts export as in class All.
    The same registry takes `--account LABEL`: an entry whose account differs prints `<id>: skipped - account <its account>`,
    needs no fetched folder, writes nothing and exits 0 for it. Without the flag every entry exports as before."""
    WAIT = "page01"
    EXTERNAL = ["ext%03d" % n for n in range(1, 9)]  # the eight pages of the other account, with synthetic ids

    def waiting(self):
        return {"id": self.WAIT, "url": "https://claude.ai/artifact/" + self.WAIT, "role": "waiting-page", "account": "work"}

    def external(self, entry_id, held=True, **changes):
        """An artifact of the other account. `held` (the default) adds `export` false: the repo holds the page, never exports it."""
        entry = {"id": entry_id, "url": "https://claude.ai/artifact/" + entry_id, "role": "page", "account": "other-account"}
        if held:
            entry["export"] = False
        return dict(entry, **changes)

    def repo(self, entries):
        root = os.path.join(self.tmp.name, "repo")
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps({"kinds": {}, "artifacts": entries}))
        return root

    def fetched_waiting(self, also=()):
        """The fetched folder a session makes when the other account cannot be read: the waiting page's folder only. `also`
        names more ids whose folders are fetched too, each shaped as the waiting page's."""
        root = tempfile.mkdtemp(prefix="fetched-all-", dir=self.tmp.name)
        for entry_id in (self.WAIT,) + tuple(also):
            fetched = self.fetch(items={"i1": item(1)}, answers={"a1": {"item": "i1", "pick": "a"}},
                                 groups={"g1": {"name": "Group"}}, asks={"k1": {"item": "i1"}}, meta={"page": META})
            os.rename(fetched, os.path.join(root, entry_id))
        return root

    def run_all(self, root, fetched, worktree, account=None):
        args = ["--all", root, "--fetched", fetched, "--worktree", worktree]
        if account is not None:
            args += ["--account", account]
        return self.run_cmd(*args)

    def test_each_export_false_entry_prints_skipped_and_the_run_exits_0(self):
        root = self.repo([self.waiting()] + [self.external(i) for i in self.EXTERNAL])
        r = self.run_all(root, self.fetched_waiting(), self.out("worktree"))
        self.assertEqual(r.returncode, 0, "a run whose export false entries are skipped must exit 0. Output:\n" + shown(r))
        for entry_id in self.EXTERNAL:
            self.assertIn("%s: skipped - no export" % entry_id, verdict_lines(r),
                          "%s has no `skipped - no export` line. Output:\n%s" % (entry_id, shown(r)))

    def test_a_skipped_entry_holds_back_no_other_artifact_and_writes_nothing(self):
        worktree = self.out("worktree")
        root = self.repo([self.waiting(), self.external(self.EXTERNAL[0])])
        r = self.run_all(root, self.fetched_waiting(), worktree)
        self.assertIn("%s: changed 5" % self.WAIT, verdict_lines(r),
                      "the waiting page was held back by a skipped entry. Output:\n" + shown(r))
        self.assertFalse(os.path.exists(os.path.join(worktree, "artifacts", self.EXTERNAL[0])),
                         "a skipped entry wrote its artifacts folder")

    def test_a_registry_of_only_export_false_entries_exits_0(self):
        fetched = self.out("fetched")
        os.makedirs(fetched)
        root = self.repo([self.external(i) for i in self.EXTERNAL[:2]])
        r = self.run_all(root, fetched, self.out("worktree"))
        self.assertEqual(r.returncode, 0, "a registry of only export false entries must exit 0. Output:\n" + shown(r))
        for entry_id in self.EXTERNAL[:2]:
            self.assertIn("%s: skipped - no export" % entry_id, verdict_lines(r),
                          "%s has no `skipped - no export` line. Output:\n%s" % (entry_id, shown(r)))

    def test_an_export_that_is_true_stays_unknown_and_the_run_exits_2(self):
        """Control: an export that is neither false nor a path is refused, so the registry is unknown: exit 2, as today."""
        root = self.repo([self.waiting(), self.external(self.EXTERNAL[0], export=True, collections=["items"])])
        r = self.run_all(root, self.fetched_waiting(), self.out("worktree"))
        self.assertEqual(r.returncode, 2, "an export of true must make the run unknown with exit 2. Output:\n" + shown(r))
        self.assertTrue(says(r, "unknown"), "no unknown verdict printed. Output:\n" + shown(r))

    def test_a_waiting_page_entry_with_export_false_is_unknown_not_skipped(self):
        """The waiting page is never held: export false on its role makes the registry unknown, exit 2, as a refused entry does."""
        root = self.repo([dict(self.waiting(), export=False)])
        r = self.run_all(root, self.fetched_waiting(), self.out("worktree"))
        self.assertEqual(r.returncode, 2, "a waiting-page entry with export false must make the run unknown with exit 2. Output:\n" + shown(r))
        self.assertTrue(says(r, "unknown"), "no unknown verdict printed for a waiting-page entry with export false. Output:\n" + shown(r))
        self.assertNotIn("%s: skipped - no export" % self.WAIT, verdict_lines(r),
                         "the waiting page was skipped instead of refused. Output:\n" + shown(r))

    def test_each_other_account_entry_prints_skipped_and_the_run_exits_0(self):
        """--account LABEL: an entry whose account differs prints `<id>: skipped - account <its account>`, exits 0 for it, and
        needs no fetched folder. The eight entries here have none."""
        entries = [self.waiting()] + [self.external(i, held=False, collections=["items"]) for i in self.EXTERNAL]
        r = self.run_all(self.repo(entries), self.fetched_waiting(), self.out("worktree"), account="work")
        self.assertEqual(r.returncode, 0, "a run with --account must exit 0 when its other-account entries are skipped. Output:\n"
                         + shown(r))
        for entry_id in self.EXTERNAL:
            self.assertIn("%s: skipped - account other-account" % entry_id, verdict_lines(r),
                          "%s has no `skipped - account` line. Output:\n%s" % (entry_id, shown(r)))

    def test_an_entry_of_the_flag_account_exports_as_today_beside_the_skipped_one(self):
        """--account LABEL: an entry whose account matches exports as it does without the flag, and the waiting page does too."""
        own, other = "own001", self.EXTERNAL[0]
        matching = {"id": own, "url": "https://claude.ai/artifact/" + own, "role": "page", "account": "work",
                    "collections": ["items"]}
        entries = [self.waiting(), matching, self.external(other, held=False, collections=["items"])]
        r = self.run_all(self.repo(entries), self.fetched_waiting(also=(own,)), self.out("worktree"), account="work")
        self.assertEqual(r.returncode, 0, "a run with --account must exit 0. Output:\n" + shown(r))
        self.assertIn("%s: skipped - account other-account" % other, verdict_lines(r),
                      "the other-account entry was not skipped. Output:\n" + shown(r))
        self.assertIn("%s: changed 5" % self.WAIT, verdict_lines(r),
                      "the waiting page of the flag's account did not export. Output:\n" + shown(r))
        self.assertIn("%s: changed 1" % own, verdict_lines(r),
                      "the entry of the flag's account did not export as it does without the flag. Output:\n" + shown(r))

    def test_a_skipped_entry_writes_nothing_even_when_its_folder_was_fetched(self):
        worktree, other = self.out("worktree"), self.EXTERNAL[0]
        r = self.run_all(self.repo([self.waiting(), self.external(other, held=False, collections=["items"])]),
                         self.fetched_waiting(also=(other,)), worktree, account="work")
        self.assertEqual(r.returncode, 0, "a run with --account must exit 0. Output:\n" + shown(r))
        self.assertIn("%s: skipped - account other-account" % other, verdict_lines(r),
                      "the other-account entry was not skipped. Output:\n" + shown(r))
        self.assertFalse(os.path.exists(os.path.join(worktree, "artifacts")),
                         "a skipped entry wrote an artifacts folder although its account was not the flag's")

    def test_without_the_flag_an_other_account_entry_exports_as_today(self):
        """Control: with no --account every entry exports whatever its account, and no line says skipped."""
        other = self.EXTERNAL[0]
        r = self.run_all(self.repo([self.waiting(), self.external(other, held=False, collections=["items"])]),
                         self.fetched_waiting(also=(other,)), self.out("worktree"))
        self.assertEqual(r.returncode, 0, "a run without --account must exit 0. Output:\n" + shown(r))
        self.assertIn("%s: changed 1" % other, verdict_lines(r),
                      "an other-account entry did not export without the flag. Output:\n" + shown(r))
        self.assertEqual([line for line in verdict_lines(r) if "skipped - account" in line], [],
                         "a run without --account skipped an entry")

    def label_run(self, label):
        """--all --account LABEL over the waiting page and one other-account entry, both fetched: the run and its worktree."""
        worktree, other = self.out("worktree"), self.EXTERNAL[0]
        entries = [self.waiting(), self.external(other, held=False, collections=["items"])]
        return self.run_all(self.repo(entries), self.fetched_waiting(also=(other,)), worktree, account=label), worktree

    def test_an_account_label_no_entry_holds_is_one_unknown_line_and_exits_2(self):
        """--account LABEL that no registry entry holds: one `unknown` line that names the label, exit 2, and nothing written,
        though the fetched folders are there for the run to export."""
        r, worktree = self.label_run("nobody")
        unknown = [line for line in verdict_lines(r) if line.startswith("unknown")]
        self.assertTrue(unknown, "a label no entry holds printed no `unknown` line. Output:\n" + shown(r))
        self.assertIn("nobody", unknown[0], "the unknown line does not name the label. Output:\n" + shown(r))
        self.assertEqual(len(verdict_lines(r)), 1, "a label no entry holds must print one line. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 2, "a label no entry holds must exit 2. Output:\n" + shown(r))
        self.assertFalse(os.path.exists(worktree), "a run whose label matched no entry wrote into the copy")

    def test_an_empty_account_label_is_one_unknown_line_and_exits_2(self):
        """--account "" (an empty label), which no registry entry holds: one `unknown` line, exit 2, and nothing written."""
        r, worktree = self.label_run("")
        lines = verdict_lines(r)
        unknown = [line for line in lines if line.startswith("unknown")]
        self.assertTrue(unknown, "an empty label printed no `unknown` line. Output:\n" + shown(r))
        self.assertEqual(len(lines), 1, "an empty label must print one line. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 2, "an empty label must exit 2. Output:\n" + shown(r))
        self.assertFalse(os.path.exists(worktree), "a run whose empty label matched no entry wrote into the copy")

    def test_check_with_account_gets_the_usage_error_that_account_without_all_gets_and_writes_nothing(self):
        """--check --account LABEL: the usage error that `--account` without `--all` gets (exit 2, the text main prints), and
        nothing written. --check takes no --account, so the run refuses the flag and runs no check. The first run is the
        control: `--account` without `--all` gets that error on main already."""
        text = "--account goes with --all"
        fetched = self.fetch()
        page = write_text(os.path.join(self.tmp.name, "page-account.html"), "<!doctype html><title>Queue</title>")
        control = self.run_cmd("--fetched", fetched, "--out", self.out(), "--account", "work")
        self.assertEqual(control.returncode, 2, "the control: --account without --all must exit 2. Output:\n" + shown(control))
        self.assertIn(text, error_line(control) or "", "the control: --account without --all does not print %r. Output:\n%s"
                      % (text, shown(control)))
        before = snapshot(self.tmp.name)
        r = self.run_cmd("--check", "--fetched", fetched, "--page", page, "--account", "work")
        self.assertEqual(snapshot(self.tmp.name), before, "--check --account wrote a file. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 2, "--check --account must exit 2 with the usage error, not run the checks. Output:\n"
                         + shown(r))
        err = error_line(r)
        self.assertIsNotNone(err, "--check --account printed no usage error line. Output:\n" + shown(r))
        self.assertIn(text, err, "--check --account does not print the usage error that --account without --all prints: %s" % err)


# ---------------------------------------------------------------------------------------------- picture checks at export
# Each fetched item with a picture that is an open decision gets the page's own
# check. Item 292 is the red control in each case: on main nothing is held, so a case that holds nothing cannot show a
# false alarm alone. Each false-alarm case runs beside item 292 and fails at its scope assert on main.
PAGE_FILE = os.path.join(HERE, "page.html")
CHECKER = os.path.join(HERE, "check_designs.mjs")
HELD_SENTENCE = "The picture of option A shows nothing the focus names."  # the page's sentence for item 292
SENTENCE_TAIL = " shows nothing the focus names."  # the page's code holds this text once; the drift case edits it
assert PAGE.count(SENTENCE_TAIL) == 1, "page.html must hold the picture sentence once: the drift case edits it"


def phone(label, inner):
    """A phone-width mockup, 390 px wide, with one element `inner` that holds `label`. Its focus is an id, not `#pickview`."""
    return '<div style="width:390px;height:844px"><div id="%s" style="height:300px">%s</div></div>' % (inner, label)


# Item 292's shape, as a literal: two options, each with its own design, and a focus (#pickview) that neither mockup
# holds. Its owner and reply fields are left out, so the cases need no other branch to run.
ITEM_292 = {
    "id": "3d-dummy-phone", "n": 292, "kind": "decision", "status": "open",
    "title": "3D dummy on a phone: where does an item's detail panel sit?", "short": "3D dummy phone panel",
    "context": "Goal: on a phone, you can read an item's detail and still see where it sits in the scene.",
    "why": "Recommended a: the scene stays in view while you read.",
    "options": [
        {"design": "3d-phone-a", "gain": "The scene stays in view while you read.",
         "how": "Tap an item; its detail opens below the scene.", "key": "a", "label": "Panel under the scene",
         "lose": "You scroll to reach the detail."},
        {"design": "3d-phone-b", "gain": "The detail shows at once, with no scroll.",
         "how": "Tap an item; its detail slides up over the scene.", "key": "b", "label": "Panel over the scene",
         "lose": "It covers the scene until you close it."},
    ],
    "designs": [
        {"file": "docs/design/3d-browser-dummy/phone-a.html", "focus": "#pickview", "label": "a: under the scene",
         "slug": "3d-phone-a"},
        {"file": "docs/design/3d-browser-dummy/phone-b.html", "focus": "#pickview", "label": "b: over the scene",
         "slug": "3d-phone-b"},
    ],
    "pick": "a", "rank": 4,
}
MOCKS_292 = {"3d-phone-a": phone("Panel under the scene", "scene-a"), "3d-phone-b": phone("Panel over the scene", "scene-b")}
GOOD_MOCKS = {"good-a": phone("Panel under", "panel-under"), "good-b": phone("Panel over", "panel-over")}


def good_item(n=301, doc_id="pick-the-panel"):
    """A two-option decision, each focus found in its own mockup: no fault, so no hold."""
    return {
        "id": doc_id, "n": n, "kind": "decision", "status": "open", "title": "Which panel position reads better?",
        "short": "Panel position", "context": "Two mockups of the same detail panel, one under the scene, one over it.",
        "why": "Both positions are drawn at phone width.",
        "options": [
            {"design": "good-a", "gain": "The scene stays in view.", "how": "The panel sits under the scene.", "key": "a",
             "label": "Panel under", "lose": "You scroll to reach it."},
            {"design": "good-b", "gain": "The detail shows at once.", "how": "The panel covers the scene.", "key": "b",
             "label": "Panel over", "lose": "It hides the scene."},
        ],
        "designs": [{"focus": "#panel-under", "label": "under", "slug": "good-a"},
                    {"focus": "#panel-over", "label": "over", "slug": "good-b"}],
    }


def picture_item(n, doc_id, **changes):
    """Item 292's bad picture under another id and number: the same shape, for the cases that must not hold it."""
    return dict(ITEM_292, id=doc_id, n=n, **changes)


def page_with_mockups(mockups, page=PAGE):
    """The page with its designData block holding `mockups` (slug to HTML). A `<` is escaped, as the page's own block is."""
    body = json.dumps(mockups, sort_keys=True).replace("<", "\\u003c")
    return DESIGN.sub(lambda m: m.group(1) + body + m.group(3), page, count=1)


def held_lines(r):
    """(n, sentence) of each `held item <n>: <sentence>` line the run printed. An --all line may carry an id before it."""
    found = []
    for line in verdict_lines(r):
        hit = re.search(r"\bheld item (\d+): (.+)$", line)
        if hit:
            found.append((int(hit.group(1)), hit.group(2)))
    return found


_CHECKER = {}  # the probe's answer, once per run: None when the check can run here, else why it cannot


def checker_problem():
    """None when node, Playwright and Chromium run the page's check here, else why not. One probe per run: the checker loads
    the real page with an item that holds no picture, so it reaches Chromium and nothing else."""
    if "why" not in _CHECKER:
        _CHECKER["why"] = probe_checker()
    return _CHECKER["why"]


def probe_checker():
    if not shutil.which("node"):
        return "node is not on PATH"
    item = write_text(os.path.join(RUN_FOLDER, "probe-item.json"), json.dumps(
        {"id": "probe", "n": 1, "kind": "decision", "status": "open", "title": "Probe",
         "options": [{"key": "a", "label": "A", "gain": "g", "lose": "l", "how": "h"}]}))
    try:
        run = subprocess.run(["node", CHECKER, "--page", PAGE_FILE, "--item", item], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "the checker did not answer in 120 s"
    if run.returncode == 0:
        return None
    lines = (run.stderr + run.stdout).strip().splitlines()
    return lines[-1] if lines else "the checker exited %d" % run.returncode


class Copied(Base):
    """The scope assert of the picture cases: a file is in the copy before a case reads what the check said about it."""

    def assertCopied(self, r, out, *rels):
        """Scope before subject: each file is in the copy, so a held line is the check's word on a doc that was exported."""
        for rel in rels:
            self.assertTrue(os.path.isfile(os.path.join(out, *rel.split("/"))),
                            "%s is not in the copy. Output:\n%s" % (rel, shown(r)))


class PictureChecks(Copied):
    """A case that runs the page's check. Where node, Playwright or Chromium is absent it skips; in CI it fails, so a
    skip never passes the case unrun."""

    def setUp(self):
        super().setUp()
        why = checker_problem()
        if why is None:
            return
        if os.environ.get("CI"):
            self.fail("the picture check cannot run in CI, so the case would pass unrun: " + why)
        self.skipTest("the picture check cannot run here: " + why)


class PictureHold(PictureChecks):
    """Item 292 is held at export: the page's own sentence, exit 4, and the copy written as today."""

    def test_item_292_is_held_at_export_and_its_copy_is_still_written(self):
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-292.html"), page_with_mockups(MOCKS_292))
        out = self.out()
        r = self.export(fetched, out, page=page)
        self.assertChanged(r, 4)  # scope: a refused export prints no verdict; the copy holds item 292, the meta doc, the page's two files
        self.assertCopied(r, out, "items/3d-dummy-phone.json", "page/page.html", "page/designData.json")
        self.assertEqual(held_lines(r), [(292, HELD_SENTENCE)],
                         "item 292 is not held with the page's sentence. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "a held item must exit 4. Output:\n" + shown(r))
        lines = verdict_lines(r)
        held_at = next(i for i, line in enumerate(lines) if line.startswith("held item 292: "))
        self.assertLess(lines.index("changed 4"), held_at, "the held line comes before the verdict line. Output:\n" + shown(r))

    def test_the_held_sentence_is_the_pages_own_not_a_copy_in_the_exporter(self):
        """The sentence comes from the page's code, so an edited page changes the held line. A copy in the exporter does not."""
        edited = page_with_mockups(MOCKS_292).replace(SENTENCE_TAIL, " shows nothing the focus names (edited page).", 1)
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-edited.html"), edited)
        out = self.out()
        r = self.export(fetched, out, page=page)
        self.assertChanged(r, 4)  # scope: the copy is written before the sentence is read
        self.assertEqual(held_lines(r), [(292, "The picture of option A shows nothing the focus names (edited page).")],
                         "the held line is not the edited page's own sentence. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "a held item must exit 4. Output:\n" + shown(r))


class PictureFalseAlarm(PictureChecks):
    """A good item is not held. Each case also holds item 292 in the same fetch. Its held line proves the check ran
    on this export, so a good item left unheld is a real pass, not a check that never ran."""

    def test_a_good_item_beside_item_292_is_not_held(self):
        good = good_item()
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292, good["id"]: good}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-pair.html"), page_with_mockups({**MOCKS_292, **GOOD_MOCKS}))
        out = self.out()
        r = self.export(fetched, out, page=page)
        self.assertChanged(r, 5)  # scope: both items, the meta doc and the page's two files are in the copy
        self.assertCopied(r, out, "items/pick-the-panel.json", "items/3d-dummy-phone.json")
        held = held_lines(r)
        self.assertIn((292, HELD_SENTENCE), held,
                      "scope: item 292 is not held, so the check did not run on this export. Output:\n" + shown(r))
        self.assertEqual([n for n, _ in held if n != 292], [], "a good item was held beside item 292. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "a held item must exit 4. Output:\n" + shown(r))

    def test_a_good_item_alone_exports_as_today(self):
        """Control for today's output: a good item and no held line, exit 0. It holds on main as well, so it guards the build."""
        good = good_item()
        fetched = self.fetch(items={good["id"]: good}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-good.html"), page_with_mockups(GOOD_MOCKS))
        out = self.out()
        r = self.export(fetched, out, page=page)
        self.assertChanged(r, 4)  # scope: the item, the meta doc and the page's two files are in the copy
        self.assertCopied(r, out, "items/pick-the-panel.json")
        self.assertEqual(held_lines(r), [], "a good item was held. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "a good item alone must export with exit 0. Output:\n" + shown(r))

    def test_an_answered_ruling_or_closed_item_beside_item_292_is_not_held(self):
        items = {
            ITEM_292["id"]: ITEM_292,
            "answered-panel": picture_item(302, "answered-panel"),
            "ruling-panel": picture_item(303, "ruling-panel", status="closed", arbiter=True),
            "closed-panel": picture_item(304, "closed-panel", status="closed"),
        }
        answers = {"answered-panel": {"item": "answered-panel", "pick": "a", "note": "Synthetic answer"}}
        fetched = self.fetch(items=items, answers=answers, meta={"page": META})
        out = self.out()
        r = self.export(fetched, out, page=write_text(os.path.join(self.tmp.name, "page-skips.html"), page_with_mockups(MOCKS_292)))
        self.assertChanged(r, 8)  # scope: four items, the answer, the meta doc and the page's two files are in the copy
        self.assertCopied(r, out, "items/answered-panel.json", "items/ruling-panel.json", "items/closed-panel.json")
        held = held_lines(r)
        self.assertIn((292, HELD_SENTENCE), held,
                      "scope: item 292 is not held, so the check did not run on this export. Output:\n" + shown(r))
        self.assertEqual([n for n, _ in held if n != 292], [],
                         "an answered, ruling or closed item was held beside item 292. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "a held item must exit 4. Output:\n" + shown(r))

    def test_an_answered_ruling_or_closed_item_alone_is_not_held(self):
        """Control for today's output: no open decision, so no check and no hold, exit 0. It holds on main as well."""
        items = {
            "answered-panel": picture_item(302, "answered-panel"),
            "ruling-panel": picture_item(303, "ruling-panel", status="closed", arbiter=True),
            "closed-panel": picture_item(304, "closed-panel", status="closed"),
        }
        answers = {"answered-panel": {"item": "answered-panel", "pick": "a", "note": "Synthetic answer"}}
        fetched = self.fetch(items=items, answers=answers, meta={"page": META})
        out = self.out()
        r = self.export(fetched, out, page=write_text(os.path.join(self.tmp.name, "page-skips-alone.html"),
                                                       page_with_mockups(MOCKS_292)))
        self.assertChanged(r, 7)  # scope: three items, the answer, the meta doc and the page's two files are in the copy
        self.assertCopied(r, out, "items/answered-panel.json", "items/ruling-panel.json", "items/closed-panel.json")
        self.assertEqual(held_lines(r), [], "an answered, ruling or closed item was held. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "no open decision must export with exit 0. Output:\n" + shown(r))


class PictureHoldFullSize(PictureChecks):
    """Full size: 120 plain items, 7 answers, 3 groups, 2 asks and the meta, with item 292 among them. Only 292 is held."""

    def test_a_full_size_fetch_holds_only_item_292(self):
        full = full_size()
        items = dict(full["items"])
        items[ITEM_292["id"]] = ITEM_292
        fetched = self.fetch(items=items, answers=full["answers"], groups=full["groups"], asks=full["asks"], meta=full["meta"])
        docs = len(items) + len(full["answers"]) + len(full["groups"]) + len(full["asks"]) + len(full["meta"])
        page = write_text(os.path.join(self.tmp.name, "page-full.html"), page_with_mockups(MOCKS_292))
        out = self.out()
        r = self.export(fetched, out, page=page)
        self.assertChanged(r, docs + 2)  # scope: every doc and the page's two files are in the copy
        self.assertCopied(r, out, "items/3d-dummy-phone.json", "items/item-120.json")
        held = held_lines(r)
        self.assertIn((292, HELD_SENTENCE), held,
                      "scope: item 292 is not held, so the check did not run on the full-size fetch. Output:\n" + shown(r))
        self.assertEqual([n for n, _ in held if n != 292], [], "a plain item was held beside item 292. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "a held item must exit 4. Output:\n" + shown(r))


class PictureHoldAll(PictureChecks):
    """--all: the waiting-page entry runs the same check, and its held line keeps the same sentence."""

    def test_the_waiting_page_entry_of_all_holds_item_292(self):
        root = os.path.join(self.tmp.name, "repo")
        registry = {"kinds": {}, "artifacts": [{"id": "page01", "url": "https://claude.ai/artifact/page01",
                                                "role": "waiting-page", "account": "work"}]}
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps(registry))
        folder = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        write_bytes(os.path.join(folder, "page.html"), page_with_mockups(MOCKS_292).encode("utf-8"))
        fetched = os.path.join(self.tmp.name, "fetched-all")
        os.makedirs(fetched)
        os.rename(folder, os.path.join(fetched, "page01"))
        worktree = self.out("worktree")
        r = self.run_cmd("--all", root, "--fetched", fetched, "--worktree", worktree)
        self.assertTrue(any("changed 4" in line for line in verdict_lines(r)),
                        "the waiting-page entry did not export its four files. Output:\n" + shown(r))
        self.assertTrue(os.path.isfile(os.path.join(worktree, "waiting", "items", "3d-dummy-phone.json")),
                        "item 292 is not in the waiting copy. Output:\n" + shown(r))
        self.assertEqual(held_lines(r), [(292, HELD_SENTENCE)],
                         "--all did not hold item 292 with the page's sentence. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "--all with a held item must exit 4. Output:\n" + shown(r))


class PictureUnknown(Copied):
    """The check cannot run: the copy is still written, one `checks unknown:` line says why, and the exit code is as without
    checks. Not gated: this case runs with node absent on purpose."""

    def test_without_node_on_the_path_the_checks_are_unknown_and_the_copy_is_written(self):
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-no-node.html"), page_with_mockups(MOCKS_292))
        out = self.out()
        empty = os.path.join(self.tmp.name, "no-node")  # a PATH with no node in it, as the no-git case does for git
        os.makedirs(empty)
        r = self.run_cmd("--fetched", fetched, "--out", out, "--page", page,
                         env=dict(os.environ, PATH=empty, PYTHONDONTWRITEBYTECODE="1"))
        self.assertChanged(r, 4)  # scope: the copy is written with no check: item, meta doc, page's two files
        self.assertCopied(r, out, "items/3d-dummy-phone.json", "page/page.html")
        unknown = [line for line in verdict_lines(r) if line.startswith("checks unknown: ")]
        self.assertEqual(len(unknown), 1, "no `checks unknown: <why>` line was printed. Output:\n" + shown(r))
        others = [line for line in verdict_lines(r) if re.search(r"\bchecks?\b", line, re.I) and not line.startswith("checks unknown: ")]
        self.assertEqual(others, [], "a check line other than `checks unknown:` was printed, such as a pass line. Output:\n" + shown(r))
        self.assertEqual(held_lines(r), [], "an unknown check held an item. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "an unknown check must exit as without checks, 0 here. Output:\n" + shown(r))


class PictureNoItems(Copied):
    """Empty state: no item, so no check and no hold. The copy holds the page's two files and nothing else. Not gated."""

    def test_an_empty_items_fetch_with_the_292_page_holds_nothing(self):
        fetched = self.fetch(items={}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-empty.html"), page_with_mockups(MOCKS_292))
        out = self.out()
        r = self.export(fetched, out, page=page)
        self.assertChanged(r, 3)  # scope: the meta doc and the page's two files are in the copy
        self.assertCopied(r, out, "page/page.html", "page/designData.json")
        self.assertEqual(held_lines(r), [], "an empty fetch held an item. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "an empty fetch must exit 0. Output:\n" + shown(r))


# ------------------------------------------------------------------------------------- --check: the checks, no write
# `export_page.py --check --fetched DIR --page FILE` runs the export's item checks and writes nothing. Each case
# compares the whole run folder before and after the run, so a write anywhere shows.
class CheckMode(PictureChecks):
    """--check with node, Playwright and Chromium present: item 292 is held, a good item passes."""

    def test_check_mode_holds_item_292_and_writes_nothing(self):
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-check-292.html"), page_with_mockups(MOCKS_292))
        before = snapshot(self.tmp.name)
        r = self.run_cmd("--check", "--fetched", fetched, "--page", page)
        self.assertEqual(snapshot(self.tmp.name), before, "--check wrote a file. Output:\n" + shown(r))
        self.assertEqual(held_lines(r), [(292, HELD_SENTENCE)],
                         "--check did not hold item 292 with the page's sentence. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "--check with a held item must exit 4. Output:\n" + shown(r))

    def test_check_mode_passes_a_good_item_and_writes_nothing(self):
        good = good_item()
        fetched = self.fetch(items={good["id"]: good}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-check-good.html"), page_with_mockups(GOOD_MOCKS))
        before = snapshot(self.tmp.name)
        r = self.run_cmd("--check", "--fetched", fetched, "--page", page)
        self.assertEqual(snapshot(self.tmp.name), before, "--check wrote a file. Output:\n" + shown(r))
        self.assertIn("checks pass", verdict_lines(r), "a clean --check did not print the line `checks pass`. Output:\n" + shown(r))
        self.assertEqual(held_lines(r), [], "--check held a good item. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "a clean --check must exit 0. Output:\n" + shown(r))


class CheckModeUnknown(Copied):
    """--check with node absent from PATH: one `checks unknown:` line, exit 3, and nothing written. Not gated: node absent
    on purpose."""

    def test_check_mode_without_node_is_unknown_and_writes_nothing(self):
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-check-no-node.html"), page_with_mockups(MOCKS_292))
        empty = os.path.join(self.tmp.name, "check-no-node")  # a PATH with no node in it
        os.makedirs(empty)
        before = snapshot(self.tmp.name)
        r = self.run_cmd("--check", "--fetched", fetched, "--page", page,
                         env=dict(os.environ, PATH=empty, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(snapshot(self.tmp.name), before, "--check wrote a file. Output:\n" + shown(r))
        unknown = [line for line in verdict_lines(r) if line.startswith("checks unknown: ")]
        self.assertEqual(len(unknown), 1, "--check printed no `checks unknown: <why>` line. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 3, "an unknown --check must exit 3. Output:\n" + shown(r))


# ------------------------------------------------------- no page file, the exit rank, answers on the page, the budget


class NoPageFile(Copied):
    """No page file, so no check can run: one `checks unknown: no page file` line, the copy written, exit 0 as today.
    Not gated: no check runs."""

    def test_a_single_export_without_a_page_names_the_missing_page(self):
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        out = self.out()
        r = self.run_cmd("--fetched", fetched, "--out", out)
        self.assertCopied(r, out, "items/3d-dummy-phone.json")  # scope: the copy is written with no page
        self.assertTrue(any(line.endswith("checks unknown: no page file") for line in verdict_lines(r)),
                        "a single export with no page printed no `checks unknown: no page file` line. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "a missing page must leave the exit code as without checks, 0. Output:\n" + shown(r))

    def test_an_all_entry_without_its_page_names_the_missing_page(self):
        root = os.path.join(self.tmp.name, "repo")
        registry = {"kinds": {}, "artifacts": [{"id": "page01", "url": "https://claude.ai/artifact/page01",
                                                "role": "waiting-page", "account": "work"}]}
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps(registry))
        folder = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})  # no page.html in this folder
        fetched = os.path.join(self.tmp.name, "fetched-no-page")
        os.makedirs(fetched)
        os.rename(folder, os.path.join(fetched, "page01"))
        worktree = self.out("worktree")
        r = self.run_cmd("--all", root, "--fetched", fetched, "--worktree", worktree)
        self.assertTrue(os.path.isfile(os.path.join(worktree, "waiting", "items", "3d-dummy-phone.json")),
                        "item 292 is not in the waiting copy. Output:\n" + shown(r))  # scope
        self.assertTrue(any(line.endswith("checks unknown: no page file") for line in verdict_lines(r)),
                        "--all printed no `checks unknown: no page file` line for the entry with no page. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "--all with no page must leave the exit code as without checks, 0. Output:\n" + shown(r))

    def test_a_plain_export_without_a_page_prints_no_check_line(self):
        """Control: plain items and no page, so no picture is checked and no check line is printed. Exit 0, as today.
        It holds on main as well."""
        fetched = self.fetch(items={"plain": item(1)}, meta={"page": META})
        out = self.out()
        r = self.run_cmd("--fetched", fetched, "--out", out)
        self.assertCopied(r, out, "items/plain.json")  # scope: the plain item is in the copy
        self.assertFalse(any("checks" in line for line in verdict_lines(r)),
                         "a check line was printed for an export with no picture. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "an export with no picture must exit 0. Output:\n" + shown(r))


class ExitRank(PictureChecks):
    """--all with one artifact held and another refused or unknown: the exit is that code, not 4. Held is 4 only when
    nothing worse happened."""

    def repo(self):
        root = os.path.join(self.tmp.name, "repo")
        registry = {"kinds": {}, "artifacts": [
            {"id": "page01", "url": "https://claude.ai/artifact/page01", "role": "waiting-page", "account": "work"},
            {"id": "queue02", "url": "https://claude.ai/artifact/queue02", "role": "queue-page", "account": "work",
             "collections": ["items"]}]}
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps(registry))
        return root

    def fetched(self, queue_page, queue_marker=True, queue_extra=()):
        """page01 holds item 292 with its mockup page, so it is held. queue02 holds one plain item and `queue_page`."""
        root = os.path.join(self.tmp.name, "fetched-rank")
        os.makedirs(root)
        waiting = self.fetch(items={ITEM_292["id"]: ITEM_292}, meta={"page": META})
        write_bytes(os.path.join(waiting, "page.html"), page_with_mockups(MOCKS_292).encode("utf-8"))
        os.rename(waiting, os.path.join(root, "page01"))
        queue = self.fetch(items={"q1": item(2)})
        write_bytes(os.path.join(queue, "page.html"), queue_page)
        for rel, data in queue_extra:
            write_text(os.path.join(queue, *rel.split("/")), data)
        if not queue_marker:
            os.remove(os.path.join(queue, "items", MARKER))
        os.rename(queue, os.path.join(root, "queue02"))
        return root

    def test_a_refused_artifact_outranks_a_held_item_in_the_exit(self):
        fetched = self.fetched(("<p>Token: %s</p>" % TOKEN).encode("utf-8"))
        r = self.run_cmd("--all", self.repo(), "--fetched", fetched, "--worktree", self.out("worktree"))
        self.assertIn((292, HELD_SENTENCE), held_lines(r),
                      "scope: item 292 is not held, so the held artifact did not run its check. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 1, "a refused artifact beside a held one must exit 1, not 4. Output:\n"
                         + shown(r, (TOKEN,)))

    def test_a_crash_beside_a_held_item_exits_3_not_4(self):
        """The queue's item file nests past the interpreter's limit, so its export crashes: a verdict of 3. A held
        item beside it must not hide the crash."""
        fetched = self.fetched(b"<p>plain queue page</p>", queue_extra=(("items/deep.json", DEEP),))
        r = self.run_cmd("--all", self.repo(), "--fetched", fetched, "--worktree", self.out("worktree"))
        self.assertIn((292, HELD_SENTENCE), held_lines(r),
                      "scope: item 292 is not held, so the held artifact did not run its check. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 3, "a crashed artifact beside a held one must exit 3, not 4. Output:\n" + shown(r))

    def test_an_unknown_artifact_outranks_a_held_item_in_the_exit(self):
        fetched = self.fetched(b"<p>plain queue page</p>", queue_marker=False)
        r = self.run_cmd("--all", self.repo(), "--fetched", fetched, "--worktree", self.out("worktree"))
        self.assertIn((292, HELD_SENTENCE), held_lines(r),
                      "scope: item 292 is not held, so the held artifact did not run its check. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 2, "an unknown artifact beside a held one must exit 2, not 4. Output:\n" + shown(r))


class AnsweredOnPage(PictureChecks):
    """An item the page draws as answered is not judged. The page's `waitsOf` decides, so the exporter's reading of a wait
    must agree with it on the run id and on the repo name."""

    def run_with(self, extra_item):
        fetched = self.fetch(items={ITEM_292["id"]: ITEM_292, extra_item["id"]: extra_item})
        out = self.out()
        r = self.export(fetched, out, page=write_text(os.path.join(self.tmp.name, "page-answers.html"),
                                                      page_with_mockups(MOCKS_292)))
        self.assertCopied(r, out, "items/%s.json" % extra_item["id"])  # scope: the item is in the copy
        self.assertIn((292, HELD_SENTENCE), held_lines(r),
                      "scope: item 292 is not held, so the check did not run on this export. Output:\n" + shown(r))
        return r

    def test_a_whole_number_run_id_read_as_a_float_is_answered_by_its_wait(self):
        """The page takes a run id that is a whole number, and 12.0 is one in JavaScript, so the page draws the item as
        answered. The exporter reads 12.0 as a float and holds the item."""
        wait = picture_item(302, "wait-float-run", waits={"repo": "owner/repo", "run": 12.0},
                            lastAnswer={"at": "2026-10-02T10:00:00Z", "note": "Synthetic wait"})
        r = self.run_with(wait)
        self.assertEqual([n for n, _ in held_lines(r) if n != 292], [],
                         "an item the page draws as answered by its wait was held. Output:\n" + shown(r))

    def test_a_wait_repo_with_a_letter_the_page_refuses_is_checked_as_open(self):
        """The page's repo pattern takes ASCII letters only, so `owner/répo` is no wait: the page draws the item as open and
        checks its picture. The exporter takes any letter, reads the item as answered, and skips the check."""
        accented = picture_item(303, "wait-accent-repo", waits={"repo": "owner/répo", "run": 12},
                                lastAnswer={"at": "2026-10-02T10:00:00Z", "note": "Synthetic wait"})
        r = self.run_with(accented)
        self.assertIn((303, HELD_SENTENCE), held_lines(r),
                      "an item the page draws as open was not checked: the exporter read its wait as answered. Output:\n"
                      + shown(r))
        self.assertEqual(r.returncode, 4, "a held item must exit 4. Output:\n" + shown(r))

    def test_control_a_whole_number_run_id_is_answered_by_its_wait(self):
        """Control: an integer run id is answered on both sides, so the item is not held. It holds on main as well."""
        wait = picture_item(304, "wait-int-run", waits={"repo": "owner/repo", "run": 12},
                            lastAnswer={"at": "2026-10-02T10:00:00Z", "note": "Synthetic wait"})
        r = self.run_with(wait)
        self.assertEqual([n for n, _ in held_lines(r) if n != 292], [],
                         "an item answered by its wait was held. Output:\n" + shown(r))


class CheckBudget(Copied):
    """One time budget for the whole run: the picture checks of one export, or of one --check, share it. A stubbed run takes
    SLOW_RUN seconds on the fake clock, longer than any budget a run is given, so the first run spends the budget and the
    rest are unknown. The per-run seam and the clock are stubbed in process, and the clock is fake: it moves only when a
    stubbed run ends, so no wall clock is read. Not gated: no node runs."""

    SLOW_RUN = 100000.0  # seconds one stubbed run takes on the fake clock
    UNKNOWN = "checks unknown: time budget spent, 2 item(s) not checked"  # 3 pictured items, and the first is checked

    class Clock:
        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            return self.now

        def perf_counter(self):
            return self.now

        def time(self):
            return self.now

    def slow_runs(self, clock, calls, tick=SLOW_RUN, held=()):
        """A stubbed run that takes `tick` on the fake clock and passes, so an item the budget leaves unchecked is the only
        unknown a case can see. A tick of 0 is the fast run. An item whose id is in `held` fails with the page's sentence."""
        def run(page_file, item, *args, **kwargs):
            calls.append(item["id"])
            clock.now += tick
            if item["id"] in held:
                return 1, HELD_SENTENCE
            return 0, ""
        return run

    def patched(self, clock, calls, tick=SLOW_RUN, held=()):
        """The per-run seam and the clock, stubbed in both modules that read the budget: `with self.patched(clock, calls):`."""
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(page_check, "run_check_designs", self.slow_runs(clock, calls, tick, held)))
        for module in (page_check, export_page):
            stack.enter_context(mock.patch.object(module, "time", clock, create=True))
        return stack

    def pictured(self):
        return {"budget-%d" % k: picture_item(300 + k, "budget-%d" % k) for k in range(1, 4)}

    def test_export_stops_at_the_budget_when_each_run_is_slow(self):
        clock, calls = self.Clock(), []
        with self.patched(clock, calls):
            held, unknown = export_page.picture_checks(PAGE_FILE, {"items": self.pictured(), "answers": {}})
        self.assertEqual(len(calls), 1, "the export ran %d of 3 pictured items past a spent budget: %r" % (len(calls), calls))
        self.assertEqual(unknown, self.UNKNOWN, "the export did not name the unchecked items. Got %r" % (unknown,))
        self.assertEqual(held, [], "a passing run held an item: %r" % (held,))

    def test_check_mode_stops_at_the_budget_when_each_run_is_slow(self):
        clock, calls = self.Clock(), []
        fetched = self.fetch(items=self.pictured())
        page = write_text(os.path.join(self.tmp.name, "page-budget.html"), page_with_mockups(MOCKS_292))
        printed = io.StringIO()
        with self.patched(clock, calls), contextlib.redirect_stdout(printed):
            code = export_page.check_only(fetched, page)
        lines = [line.strip() for line in printed.getvalue().splitlines()]
        self.assertEqual(len(calls), 1, "--check ran %d of 3 pictured items past a spent budget: %r" % (len(calls), calls))
        self.assertIn(self.UNKNOWN, lines, "--check did not name the unchecked items. Output:\n" + printed.getvalue())
        self.assertNotIn("checks pass", lines, "--check read the unchecked items as a pass. Output:\n" + printed.getvalue())
        self.assertEqual(code, 3, "--check with the budget spent must exit 3, unknown. Output:\n" + printed.getvalue())

    def test_check_mode_held_item_beside_a_spent_budget_exits_4(self):
        """The first item is held and spends the budget, so two are unchecked. The held line prints, the unknown line prints,
        and the exit is 4: a held item outranks the unknown 3."""
        clock, calls = self.Clock(), []
        fetched = self.fetch(items=self.pictured())
        page = write_text(os.path.join(self.tmp.name, "page-budget-held.html"), page_with_mockups(MOCKS_292))
        printed = io.StringIO()
        with self.patched(clock, calls, held=("budget-1",)), contextlib.redirect_stdout(printed):
            code = export_page.check_only(fetched, page)
        lines = [line.strip() for line in printed.getvalue().splitlines()]
        self.assertEqual(calls, ["budget-1"], "scope: the held item did not run alone before the budget was spent: %r" % (calls,))
        self.assertIn("held item 301: " + HELD_SENTENCE, lines,
                      "--check did not print the held item's line. Output:\n" + printed.getvalue())
        self.assertIn(self.UNKNOWN, lines, "--check did not print the unchecked items' line. Output:\n" + printed.getvalue())
        self.assertEqual(code, 4, "--check with a held item and the budget spent must exit 4, not 3. Output:\n" + printed.getvalue())

    def test_export_keeps_its_copy_and_its_exit_when_the_budget_is_spent(self):
        clock, calls = self.Clock(), []
        fetched = self.fetch(items=self.pictured(), meta={"page": META})
        page = write_text(os.path.join(self.tmp.name, "page-budget-export.html"), page_with_mockups(MOCKS_292))
        out = self.out()
        printed = io.StringIO()
        with self.patched(clock, calls), contextlib.redirect_stdout(printed):
            code = export_page.main(["--fetched", fetched, "--out", out, "--page", page])
        lines = [line.strip() for line in printed.getvalue().splitlines()]
        for n in (1, 2, 3):
            self.assertTrue(os.path.isfile(os.path.join(out, "items", "budget-%d.json" % n)),
                            "scope: budget-%d is not in the copy, so the export did not write every item. Output:\n%s"
                            % (n, printed.getvalue()))
        self.assertIn(self.UNKNOWN, lines, "the export did not name the unchecked items. Output:\n" + printed.getvalue())
        self.assertEqual(code, 0, "an export with the budget spent and no held item must keep its exit code, 0. Output:\n"
                         + printed.getvalue())


    def test_control_export_checks_every_item_when_each_run_is_fast(self):
        """Control: fast runs spend no budget, so all three items are checked and none is unknown. It holds without the budget too."""
        clock, calls = self.Clock(), []
        with self.patched(clock, calls, tick=0.0):
            held, unknown = export_page.picture_checks(PAGE_FILE, {"items": self.pictured(), "answers": {}})
        self.assertEqual(len(calls), 3, "the export ran %d of 3 pictured items when each run is fast: %r" % (len(calls), calls))
        self.assertIsNone(unknown, "the export named an unknown when no budget was spent: %s" % (unknown,))
        self.assertEqual(held, [], "a passing run held an item: %r" % (held,))

    def test_control_check_mode_passes_every_item_when_each_run_is_fast(self):
        """Control: --check with fast runs checks all three and prints `checks pass`, exit 0. It holds without the budget too."""
        clock, calls = self.Clock(), []
        fetched = self.fetch(items=self.pictured())
        page = write_text(os.path.join(self.tmp.name, "page-budget-fast.html"), page_with_mockups(MOCKS_292))
        printed = io.StringIO()
        with self.patched(clock, calls, tick=0.0), contextlib.redirect_stdout(printed):
            code = export_page.check_only(fetched, page)
        lines = [line.strip() for line in printed.getvalue().splitlines()]
        self.assertEqual(len(calls), 3, "--check ran %d of 3 pictured items when each run is fast: %r" % (len(calls), calls))
        self.assertIn("checks pass", lines, "--check printed no `checks pass` when each run is fast. Output:\n"
                      + printed.getvalue())
        self.assertEqual(code, 0, "a clean --check must exit 0. Output:\n" + printed.getvalue())


class AnswersPassed(Copied):
    """The export gives the checker its answers even when the map is empty, as `--answers` naming a file that holds {}.
    The page's isAnswered reads those answers, so a map that is dropped on the way is a different check. The node start is
    stubbed in process, so no Chromium starts. Not gated: no node runs."""

    def started(self, call):
        """Runs `call` with the checker's start stubbed. Returns what the start got: `command`, and `answers`, the text of
        the --answers file, or None when the flag was not passed."""
        seen = {"answers": None}

        def start(command, *args, **kwargs):
            seen["command"] = list(command)
            if "--answers" in command:
                with open(command[command.index("--answers") + 1], encoding="utf-8") as handle:
                    seen["answers"] = handle.read()
            return subprocess.CompletedProcess(command, 0, '{"problem": null}\n', "")

        with mock.patch.object(_nowindow, "run", start), \
                mock.patch.object(page_check.shutil, "which", return_value="/usr/bin/node"):
            call()
        return seen

    def test_an_empty_answers_map_reaches_the_checker_as_answers(self):
        waiting = picture_item(305, "wait-empty-map", waits={"repo": "owner/repo", "run": 12},
                               lastAnswer={"at": "2026-10-02T10:00:00Z", "note": "Synthetic wait"})
        control = self.started(lambda: page_check.run_check_designs(PAGE_FILE, waiting, answers=None))
        self.assertIn("command", control, "control: the checker was not started with no answers")
        self.assertIsNone(control["answers"], "control: no answers were given, yet --answers went to the checker: %s"
                          % control["command"])
        seen = self.started(lambda: export_page.picture_checks(PAGE_FILE, {"items": {waiting["id"]: waiting}, "answers": {}}))
        self.assertIn("command", seen, "scope: the export path never started the checker, so the empty map was not tested")
        self.assertIsNotNone(seen["answers"], "the export gave the checker an empty answers map, but no --answers flag went "
                             "with it: page_check drops {} (`if answers:`), so the page's isAnswered reads no answers: %s"
                             % seen["command"])
        self.assertEqual(json.loads(seen["answers"]), {}, "the --answers file is not the empty map the export gave")


class RepublishChecksFirst(Base):
    """reference/repo-pages.md "Update a repo's pages" step 3: `export_page.py --check` runs on the `stale_pages.py --write`
    output before the republish. The step's text is read from the skill's files by skill_step, never copied here. Not gated:
    no node runs."""

    def test_step_3_runs_the_check_on_the_write_output_before_the_republish(self):
        step = " ".join(skill_step("## Update a repo's pages", 3).split())
        # The command sits in a code span, with --check and --page <new page> in any order.
        spans = [m for m in re.finditer(r"`([^`]*export_page\.py[^`]*)`", step)
                 if "--check" in m.group(1) and "--page <new page>" in m.group(1)]
        self.assertTrue(spans, "step 3 names no `export_page.py` command with --check and --page <new page> on the "
                        "`stale_pages.py --write` output, so a bad item reaches the page at republish. Step 3:\n" + step)
        republish = step.find("Republish")
        self.assertGreaterEqual(republish, 0, "step 3 has no Republish sentence, so the order cannot be read. Step 3:\n" + step)
        self.assertLess(spans[0].start(), republish, "step 3 runs the check after the republish. Step 3:\n" + step)


class WaitingCollectionsRun(Copied):
    """--all with one registry entry `entry_id` of `role`, whose own `collections` is `collections` (None: no list, so the
    waiting page gets the default five). The fetched page holds `items`, `answers` and the page with item 292's mockups.
    Returns (the run, the worktree)."""

    def run_all(self, collections, items, answers=None, role="waiting-page", entry_id="page01"):
        root = os.path.join(self.tmp.name, "repo")
        entry = {"id": entry_id, "url": "https://claude.ai/artifact/" + entry_id, "role": role, "account": "work"}
        if collections is not None:
            entry["collections"] = list(collections)
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps({"kinds": {}, "artifacts": [entry]}))
        folder = self.fetch(items=items, answers=answers, meta={"page": META})
        write_bytes(os.path.join(folder, "page.html"), page_with_mockups(MOCKS_292).encode("utf-8"))
        fetched = os.path.join(self.tmp.name, "fetched-collections")
        os.makedirs(fetched)
        os.rename(folder, os.path.join(fetched, entry_id))
        worktree = self.out("worktree")
        return self.run_cmd("--all", root, "--fetched", fetched, "--worktree", worktree), worktree


class WaitingCollections(WaitingCollectionsRun):
    """--all, a waiting-page entry whose own `collections` lacks `items` or `answers`: the picture check cannot read what it
    needs, so the entry prints `<id>: checks unknown: collections lack <name>`, its copy is written and the exit is 2. The
    unknown lines need no node, so these cases are not gated."""

    def test_a_waiting_entry_without_items_is_named_unknown_and_exits_2(self):
        r, worktree = self.run_all(("answers", "groups", "asks", "meta"), {ITEM_292["id"]: ITEM_292})
        self.assertTrue(os.path.isfile(os.path.join(worktree, "waiting", "meta", "page.json")),
                        "scope: the meta doc is not in the copy. Output:\n" + shown(r))
        self.assertIn("page01: checks unknown: collections lack items", verdict_lines(r),
                      "--all printed no `checks unknown: collections lack items` line: the picture check was skipped without a "
                      "word, and the entry reads as a pass. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 2, "a waiting page whose check cannot run must exit 2. Output:\n" + shown(r))

    def test_a_waiting_entry_without_answers_is_named_unknown_and_exits_2(self):
        r, worktree = self.run_all(("items", "groups", "asks", "meta"), {ITEM_292["id"]: ITEM_292})
        self.assertTrue(os.path.isfile(os.path.join(worktree, "waiting", "items", "3d-dummy-phone.json")),
                        "scope: item 292 is not in the copy. Output:\n" + shown(r))
        self.assertIn("page01: checks unknown: collections lack answers", verdict_lines(r),
                      "--all printed no `checks unknown: collections lack answers` line for a waiting page with no answers "
                      "collection. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 2, "a waiting page whose check cannot run must exit 2. Output:\n" + shown(r))

    def test_control_a_queue_entry_with_items_only_runs_no_check_and_exits_0(self):
        """Control: the check is the waiting page's. A queue page whose collections list only items, with a plain item, is
        exported with no check line. It holds without the budget too."""
        r, worktree = self.run_all(("items",), {"plain": item(1)}, role="queue-page", entry_id="queue02")
        self.assertTrue(os.path.isfile(os.path.join(worktree, "artifacts", "queue02", "items", "plain.json")),
                        "scope: the plain item is not in the queue copy. Output:\n" + shown(r))
        self.assertTrue(any(re.match(r"queue02: changed \d+$", line) for line in verdict_lines(r)),
                        "scope: the queue entry printed no `changed N` verdict. Output:\n" + shown(r))
        checks = [line for line in verdict_lines(r) if "checks" in line]
        self.assertEqual(checks, [], "a queue page with no waiting role was given a check line. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 0, "a queue page with a plain item must exit 0. Output:\n" + shown(r))


class WaitingCollectionsHold(WaitingCollectionsRun, PictureChecks):
    """A waiting page without its answers collection holds no item the page draws as answered, and the control with the
    answers read. Gated: the page's own check runs, so a node-less run skips here and CI fails it."""

    def answered(self):
        """Item 292 and an answers collection that holds a saved answer under its id: the page draws item 292 as answered."""
        return {ITEM_292["id"]: ITEM_292}, {ITEM_292["id"]: {"pick": "a", "note": "Synthetic answer"}}

    def test_a_waiting_entry_without_answers_holds_no_item_the_page_draws_as_answered(self):
        items, answers = self.answered()
        r, worktree = self.run_all(("items", "groups", "asks", "meta"), items, answers)
        self.assertTrue(os.path.isfile(os.path.join(worktree, "waiting", "items", "3d-dummy-phone.json")),
                        "scope: item 292 is not in the copy. Output:\n" + shown(r))
        self.assertNotIn(292, [n for n, _ in held_lines(r)],
                         "item 292 is held, though the page draws it as answered: the answers collection is not read, so the "
                         "check holds an answered item. Output:\n" + shown(r))

    def test_control_with_answers_read_the_answered_item_is_not_held_and_the_open_picture_is(self):
        """Control: with the answers collection in the registry, item 292 is not held and an open picture is, so the check
        ran. It holds on main as well."""
        items, answers = self.answered()
        items["open-picture"] = picture_item(313, "open-picture")
        r, _worktree = self.run_all(None, items, answers)
        self.assertIn((313, HELD_SENTENCE), held_lines(r),
                      "scope: the open picture, item 313, is not held, so the check did not run. Output:\n" + shown(r))
        self.assertNotIn(292, [n for n, _ in held_lines(r)],
                         "item 292 is held though its answer is read. Output:\n" + shown(r))
        self.assertEqual(r.returncode, 4, "a held item must exit 4. Output:\n" + shown(r))


if __name__ == "__main__":
    unittest.main()
