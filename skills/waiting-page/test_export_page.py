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
  Retina names are not emails: `logo@2x.png`, as a file name or in page text, exports; `jane@2x.com` refuses.
  Digit-led domains are emails: jane@1st.example.com, jane@12.34.example.com and jane@1.2.3.com refuse in page text.
  URL credentials refuse on an IP host as on a host name: postgres://app:<password>@10.0.0.5:5432/db refuses; an IP
    host with no credentials passes.
  Verdict words: `changed N`, `same`, `refused` (exit 1), `unknown` (exit 2), and a crash (exit 3, one line).
  Not pinned here: whether a supporting file no longer fetched is deleted.
"""
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CMD = os.environ.get("EXPORT_PAGE_UNDER_TEST") or os.path.join(HERE, "export_page.py")
LINT = os.path.realpath(os.path.join(HERE, "..", "..", "lint"))
sys.path.insert(0, LINT)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

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
    # A key word inside a longer name is a credential name too. The stem of an everyday word (mon, turn, hoc) is no
    # reason to skip it. The value is the one the turnkey control in GREEN uses.
    ("commonKey with a value of letters and digits", "commonKey: " + GLUED_VALUE, GLUED_VALUE),
    ("daemonKey with a value of letters and digits", "daemonKey: " + GLUED_VALUE, GLUED_VALUE),
    ("adHocKey with a value of letters and digits", "adHocKey: " + GLUED_VALUE, GLUED_VALUE),
    ("returnKey with a value of letters and digits", "returnKey: " + GLUED_VALUE, GLUED_VALUE),
    # A letters-only secret after a plain word and prose is one. The prose after the plain word must not hide it.
    ("letters-only secret after a plain word and a semicolon",
     "password: required to log in; default is swordfish", "swordfish"),
    ("letters-only secret after a plain word and `and`", "password: none and swordfish", "swordfish"),
    # A comma does not end the prose: a letters-only secret after a comma, with prose before it, is one.
    ("letters-only secret after prose and a comma", "password: none for the admin account, " + PROSE_SECRET, PROSE_SECRET),
    # The digit counts wherever it sits in the value: at 256, and at 257 and 1000 past it.
    ("digit at index 256 of a credential value", "API_KEY=" + CAP_LAST_DIGIT, CAP_LAST_DIGIT),
    ("digit at index 257 of a credential value", "API_KEY=" + DIGIT_AT_257, DIGIT_AT_257),
    ("digit at index 1000 of a credential value", "API_KEY=" + DIGIT_AT_1000, DIGIT_AT_1000),
    # The letter at index 300 is past the short shape's window, so only the long-value shape can see it. It refuses.
    ("API_KEY of 300 digits then a letter", "API_KEY=" + DIGITS_300_THEN_LETTER, DIGITS_300_THEN_LETTER),
]

# (label, the note's value). Words, a URL, a time, an id and a number that are not secrets pass.
GREEN = [
    ("token budget", "token budget"),
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
    ("prose with the word secret before a name", "the secret santa list"),
    # The names that do not count under the rule (bare token, camelCase, a hyphenated or a non-credential name) pass.
    # These four are false alarms today: each refuses on its value's length, so they are red on the builder's head.
    ("destructured token alias", "const { token: accessTokenValue } = await getSession();"),
    ("camelCase accessToken key with a call", "accessToken: localStorage.getItem('accessToken')"),
    ("CSS custom property ending in token", "--color-token: rgba(0,0,0,0.5);"),
    ("prose with Token before a sentence", "Token: Authorization needed before we continue"),
]


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

    def fetch(self, items=None, answers=None, groups=None, asks=None, meta=None):
        """A fetched folder: one folder per collection, each doc a JSON file, and the completeness marker. An empty
        collection is an empty folder with its marker."""
        root = tempfile.mkdtemp(prefix="fetched-", dir=self.tmp.name)
        docs = {"items": items, "answers": answers, "groups": groups, "asks": asks, "meta": meta}
        for name in COLLECTIONS:
            os.makedirs(os.path.join(root, name))
            for doc_id, data in (docs[name] or {}).items():
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

    def rebuild(self, waiting, batches):
        os.makedirs(batches, exist_ok=True)
        return self.run_cmd("--rebuild", waiting, "--batches", batches)

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


class All(Base):
    """--all: each artifact in the repo's registry (the "artifacts" key of its extras file) exports its collections to
    its export path under --worktree: the waiting page to waiting/, any other artifact to artifacts/<id>/. Each artifact
    gets the same scan and mirror as a single export, and one verdict line of its own, named by its id."""
    WAIT, QUEUE = "page01", "queue02"
    VERDICT = r"\b(changed\s+\d+|same|refused|unknown)\b"

    def repo(self):
        root = os.path.join(self.tmp.name, "repo")
        registry = {"kinds": {}, "artifacts": [
            {"id": self.WAIT, "url": "https://claude.ai/artifact/" + self.WAIT, "role": "waiting-page", "account": "work"},
            {"id": self.QUEUE, "url": "https://claude.ai/artifact/" + self.QUEUE, "role": "queue-page", "account": "work",
             "collections": ["items"]}]}
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps(registry))
        return root

    def docs(self):
        """What each artifact's fetch holds. The queue lists items only, so its answers are fetched but never exported."""
        return {self.WAIT: dict(items={"i1": item(1)}, answers={"a1": {"item": "i1", "pick": "a"}},
                                groups={"g1": {"name": "Group"}}, asks={"k1": {"item": "i1"}}, meta={"page": META}),
                self.QUEUE: dict(items={"q1": item(2)}, answers={"qa1": {"item": "q1", "pick": "b"}})}

    def fetched_all(self, docs, pages=None, files=None):
        """One fetched folder per artifact id, each shaped as a single fetch is. `pages` maps an id to its page.html
        bytes; `files` maps an id to {path under files/: bytes}, the page's supporting files."""
        root = tempfile.mkdtemp(prefix="fetched-all-", dir=self.tmp.name)
        for artifact_id, parts in docs.items():
            folder = self.fetch(**parts)
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
        # empty collection gets a folder only where the step says to make one by hand. The text is read from SKILL.md,
        # never copied here, so a change to that step is what this case checks.
        sections = read_text(os.path.join(HERE, "SKILL.md")).split("## Before you switch Claude accounts", 1)
        self.assertEqual(len(sections), 2, "SKILL.md has no 'Before you switch Claude accounts' section")
        steps = sections[1].split("\n## ", 1)[0].split("\n2. ", 1)
        self.assertEqual(len(steps), 2, "the 'Before you switch Claude accounts' section has no step 2")
        step2 = steps[1].split("\n3. ", 1)[0]
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
    fetched folder for it. The other artifacts export as in class All."""
    WAIT = "page01"
    EXTERNAL = ["ext%03d" % n for n in range(1, 9)]  # the eight pages of the other account, with synthetic ids

    def waiting(self):
        return {"id": self.WAIT, "url": "https://claude.ai/artifact/" + self.WAIT, "role": "waiting-page", "account": "work"}

    def external(self, entry_id, **changes):
        return dict({"id": entry_id, "url": "https://claude.ai/artifact/" + entry_id, "role": "page",
                     "account": "other-account", "export": False}, **changes)

    def repo(self, entries):
        root = os.path.join(self.tmp.name, "repo")
        write_text(os.path.join(root, ".claude", "layout-extras.json"), json.dumps({"kinds": {}, "artifacts": entries}))
        return root

    def fetched_waiting(self):
        """The fetched folder a session makes when the other account cannot be read: the waiting page's folder only."""
        root = tempfile.mkdtemp(prefix="fetched-all-", dir=self.tmp.name)
        fetched = self.fetch(items={"i1": item(1)}, answers={"a1": {"item": "i1", "pick": "a"}},
                             groups={"g1": {"name": "Group"}}, asks={"k1": {"item": "i1"}}, meta={"page": META})
        os.rename(fetched, os.path.join(root, self.WAIT))
        return root

    def run_all(self, root, fetched, worktree):
        return self.run_cmd("--all", root, "--fetched", fetched, "--worktree", worktree)

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


if __name__ == "__main__":
    unittest.main()
