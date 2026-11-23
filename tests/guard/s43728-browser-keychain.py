# section 43728
FAMILY = "browser-keychain"
# Rule browser-keychain (hooks/guard_browser.py, decision render-browser-no-keychain): a Chromium launched with no mock
# keychain. A macOS Playwright or Puppeteer Chromium asks for the owner's keychain password unless both switches are
# on the launch. These cases hold the refusals and the passes for a shell command and for a Write, Edit or MultiEdit
# of a script file. The rule judges the launches a write adds, so an edit elsewhere in a file passes.
# Each refusal below is red on the old code (no such rule: the call is allowed). Each pass is a control, green on both.

BK_REMEDY = ("--use-mock-keychain", "--password-store=basic")
BK_DIR = os.path.join(ROOT, "browser-keychain")
os.makedirs(BK_DIR, exist_ok=True)

# The fixture files the Write, Edit and MultiEdit cases judge. The guard only reads them, so each case may share one.
BK_FLAGGED_LINE = 'const b = await chromium.launch({ args: ["--use-mock-keychain", "--password-store=basic"] });'
BK_BARE_LINE = "const b = await chromium.launch();"
BK_FLAGGED = os.path.join(BK_DIR, "flagged.mjs")          # a launch that carries both switches
BK_BARE = os.path.join(BK_DIR, "bare.mjs")                # a bare launch
BK_ELSEWHERE = os.path.join(BK_DIR, "old-bare.mjs")       # a bare launch the file already held, plus a comment
BK_SECOND = os.path.join(BK_DIR, "one-bare.mjs")          # one bare launch, for a second to be added beside
BK_ADD = os.path.join(BK_DIR, "add-switches.mjs")         # one bare launch, for the switches to be added to
BK_MULTI = os.path.join(BK_DIR, "multi.mjs")              # one bare launch, judged through MultiEdit
BK_EMPTY = os.path.join(BK_DIR, "empty.mjs")              # an empty script file: the empty state
BK_LARGE = os.path.join(BK_DIR, "large.mjs")              # a full-size script file with an old bare launch in it
BK_LARGE_LINES = [BK_BARE_LINE] + ["// filler line %d" % n for n in range(3000)] + ["// tail"]
for _path, _text in ((BK_FLAGGED, BK_FLAGGED_LINE + "\n"), (BK_BARE, BK_BARE_LINE + "\n"),
                     (BK_ELSEWHERE, "// the old launch\n" + BK_BARE_LINE + "\n"),
                     (BK_SECOND, BK_BARE_LINE + "\n"), (BK_ADD, BK_BARE_LINE + "\n"),
                     (BK_MULTI, BK_BARE_LINE + "\n"), (BK_EMPTY, ""),
                     (BK_LARGE, "\n".join(BK_LARGE_LINES) + "\n")):
    with open(_path, "w", encoding="utf-8") as _f:
        _f.write(_text)

# ---- Shell commands: refused. The launch names no switch, one switch, or runs the CLI or a binary that takes none.
NODE_BARE = ("node -e \"const { chromium } = require('playwright'); (async () => { "
             "const b = await chromium.launch(); await b.close(); })()\"")
PY_BARE = ("python3 -c \"from playwright.sync_api import sync_playwright; p = sync_playwright().start(); "
           "b = p.chromium.launch(); b.close()\"")
CHROME_FOR_TESTING = ("\"/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing\" "
                      "--headless --screenshot=shot.png https://example.com")

sh("browser-keychain: inline node -e with a bare chromium.launch() is refused", NODE_BARE, "deny",
   "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: inline python3 -c with a bare chromium.launch() is refused", PY_BARE, "deny",
   "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: a node heredoc with a bare chromium.launch() is refused",
   "node <<'EOF'\n(async () => { const b = await chromium.launch(); await b.close(); })();\nEOF",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: a python heredoc with a bare chromium.launch() is refused",
   "python3 <<'EOF'\nfrom playwright.sync_api import sync_playwright\np = sync_playwright().start()\np.chromium.launch()\nEOF",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: a script the command writes with cat > and then runs is refused",
   "cat > render-it.mjs <<'EOF'\nimport { chromium } from 'playwright';\nconst b = await chromium.launch();\nEOF\nnode render-it.mjs",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: bash -c that runs a bare python launch is refused",
   "bash -c \"python3 -c 'from playwright.sync_api import sync_playwright; sync_playwright().start().chromium.launch()'\"",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: npx playwright screenshot is refused, the CLI takes no switch",
   "npx playwright screenshot https://example.com shot.png", "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: npx playwright open is refused, the CLI takes no switch",
   "npx playwright open https://example.com", "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: npx @puppeteer/browsers launch is refused",
   "npx @puppeteer/browsers launch chrome@125.0.0", "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: a Chrome for Testing binary with no switches is refused", CHROME_FOR_TESTING,
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: a Chromium binary with one switch only is refused",
   "chromium --use-mock-keychain --headless --screenshot=shot.png https://example.com",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: inline node -e with one switch only is refused",
   "node -e \"const b = require('playwright').chromium.launch({ args: ['--use-mock-keychain'] })\"",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: inline node -e with a puppeteer require().launch() and no switch is refused",
   "node -e \"require('puppeteer').launch()\"", "deny", "browser-keychain", carries=BK_REMEDY)
# A `//` and a `/*` inside a string do not hide the live launch after the string (building-scanner-respects-strings).
sh("browser-keychain: a comment opener inside a string does not hide a bare launch after it",
   "node -e \"console.log('http://x/*'); (async () => { const b = await chromium.launch(); })()\"",
   "deny", "browser-keychain", carries=BK_REMEDY)

# ---- Shell commands: allowed. The flagged launches, the other browsers, the version and help forms, and the text
# that names a launch without running one.
sh("browser-keychain: inline node -e with both switches is allowed",
   "node -e \"const { chromium } = require('playwright'); (async () => { const b = await chromium.launch({ "
   "args: ['--use-mock-keychain', '--password-store=basic'] }); await b.close(); })()\"",
   "allow", tool="Bash")
sh("browser-keychain: inline python3 -c with both switches is allowed",
   "python3 -c \"from playwright.sync_api import sync_playwright; p = sync_playwright().start(); "
   "p.chromium.launch(args=['--use-mock-keychain', '--password-store=basic'])\"",
   "allow", tool="Bash")
sh("browser-keychain: npx playwright screenshot with -b firefox is allowed",
   "npx playwright screenshot -b firefox https://example.com shot.png", "allow", tool="Bash")
sh("browser-keychain: a Chrome for Testing binary with both switches is allowed",
   "\"/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing\" "
   "--use-mock-keychain --password-store=basic --headless --screenshot=shot.png https://example.com",
   "allow", tool="Bash")
sh("browser-keychain: a Chrome for Testing binary with --version is allowed", CHROME_FOR_TESTING.replace(
   " --headless --screenshot=shot.png https://example.com", " --version"), "allow", tool="Bash")
sh("browser-keychain: node -e with a puppeteer require().launch() and both switches is allowed",
   "node -e \"require('puppeteer').launch({ args: ['--use-mock-keychain', '--password-store=basic'] })\"",
   "allow", tool="Bash")
sh("browser-keychain: the shoot tool is allowed", "shoot --file page.html --out shots", "allow", tool="Bash")
sh("browser-keychain: grep for the launch text is allowed",
   "grep -rn \"chromium.launch(\" lint/", "allow", tool="Bash")
sh("browser-keychain: echo of the launch text is allowed",
   "echo \"the rule refuses a bare chromium.launch() call\"", "allow", tool="Bash")
sh("browser-keychain: a commit message that names a bare launch is allowed",
   "git commit -m \"Refuse a bare chromium.launch() in node -e\"", "allow", tool="Bash")
sh("browser-keychain: a shell comment that names a launch is allowed",
   "echo ok  # node -e \"const b = chromium.launch()\"", "allow", tool="Bash")
sh("browser-keychain: a quoted launch inside echo is allowed",
   "echo \"node -e 'chromium.launch()'\"", "allow", tool="Bash")

# ---- Write, Edit and MultiEdit of a script file.
add("browser-keychain: a Write of a new script with a bare launch is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "new-render.mjs"),
    content="import { chromium } from 'playwright';\n" + BK_BARE_LINE + "\n", carries=BK_REMEDY)
add("browser-keychain: a Write of a Python script with a bare launch is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "new-render.py"),
    content="from playwright.sync_api import sync_playwright\np = sync_playwright().start()\nb = p.chromium.launch()\n",
    carries=BK_REMEDY)
add("browser-keychain: a Write of a shell script with the Playwright CLI is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "shot.sh"),
    content="npx playwright screenshot https://example.com shot.png\n", carries=BK_REMEDY)
add("browser-keychain: a whole-file Write of bin/shoot with a bare launch is refused",
    "deny", "browser-keychain", tool="Write", file_path=os.path.join(BK_DIR, "bin", "shoot"),
    content="#!/usr/bin/env node\n" + BK_BARE_LINE + "\n", carries=BK_REMEDY)
add("browser-keychain: a Write over an empty script with a bare launch is refused", "deny", "browser-keychain",
    tool="Write", file_path=BK_EMPTY, content=BK_BARE_LINE + "\n", carries=BK_REMEDY)
add("browser-keychain: a Write over a flagged file with the switches removed is refused", "deny",
    "browser-keychain", tool="Write", file_path=BK_FLAGGED, content=BK_BARE_LINE + "\n", carries=BK_REMEDY)
add("browser-keychain: an Edit that removes the switches is refused", "deny", "browser-keychain",
    tool="Edit", file_path=BK_FLAGGED,
    old_string='{ args: ["--use-mock-keychain", "--password-store=basic"] }', new_string="{}", carries=BK_REMEDY)
add("browser-keychain: an Edit that adds a second bare launch is refused", "deny", "browser-keychain",
    tool="Edit", file_path=BK_SECOND, old_string=BK_BARE_LINE,
    new_string=BK_BARE_LINE + "\n" + BK_BARE_LINE, carries=BK_REMEDY)
add("browser-keychain: a MultiEdit that adds a second bare launch is refused", "deny", "browser-keychain",
    tool="MultiEdit", file_path=BK_MULTI,
    edits=[{"old_string": BK_BARE_LINE, "new_string": BK_BARE_LINE + "\n" + BK_BARE_LINE}], carries=BK_REMEDY)
add("browser-keychain: a Write with a comment opener in a string does not hide a bare launch after it",
    "deny", "browser-keychain", tool="Write", file_path=os.path.join(BK_DIR, "scanner.mjs"),
    content="const url = \"http://example.com/*\";\n" + BK_BARE_LINE + "\n", carries=BK_REMEDY)
add("browser-keychain: a bare launch after a multi-line template literal is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "template.mjs"),
    content="const page = `\n  <p>chromium.launch()</p>\n`;\n" + BK_BARE_LINE + "\n", carries=BK_REMEDY)
add("browser-keychain: a lone apostrophe in JSX text does not hide a bare launch on the next line", "deny",
    "browser-keychain", tool="Write", file_path=os.path.join(BK_DIR, "note.jsx"),
    content="export const Note = () => <p>Don't stop</p>;\n" + BK_BARE_LINE + "\n", carries=BK_REMEDY)
add("browser-keychain: a Write of named args with one switch only is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "named-one.mjs"),
    content='const ARGS = ["--use-mock-keychain"];\nconst b = await chromium.launch({ args: ARGS });\n',
    carries=BK_REMEDY)

add("browser-keychain: a Write of a new script with both switches is allowed", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "new-flagged.mjs"), content=BK_FLAGGED_LINE + "\n")
add("browser-keychain: a Write of named args that holds both switches is allowed", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "named-both.mjs"),
    content='const ARGS = ["--use-mock-keychain", "--password-store=basic"];\nconst b = await chromium.launch({ args: ARGS });\n')
add("browser-keychain: a Write of a Python script with both switches is allowed", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "flagged.py"),
    content="p = sync_playwright().start()\np.chromium.launch(args=['--use-mock-keychain', '--password-store=basic'])\n")
add("browser-keychain: a Write of a commented-out launch is allowed", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "commented.mjs"), content="// " + BK_BARE_LINE + "\nexport const x = 1;\n")
add("browser-keychain: a Write of a block-commented launch is allowed", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "block.mjs"), content="/* " + BK_BARE_LINE + " */\nexport const x = 1;\n")
add("browser-keychain: a launch inside a multi-line template literal is allowed", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "doc.mjs"), content="const page = `\n  " + BK_BARE_LINE + "\n`;\nexport default page;\n")
add("browser-keychain: a bare launch in a markdown file is not judged", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "notes.md"), content="```js\n" + BK_BARE_LINE + "\n```\n")
add("browser-keychain: an Edit that adds the switches to a bare launch is allowed", "allow", tool="Edit",
    file_path=BK_ADD, old_string="chromium.launch();",
    new_string='chromium.launch({ args: ["--use-mock-keychain", "--password-store=basic"] });')
add("browser-keychain: an Edit that adds a second flagged launch is allowed", "allow", tool="Edit",
    file_path=BK_FLAGGED, old_string="const b = ",
    new_string='const c = await chromium.launch({ args: ["--use-mock-keychain", "--password-store=basic"] });\nconst b = ')
add("browser-keychain: an Edit elsewhere in a file with an old bare launch is allowed", "allow", tool="Edit",
    file_path=BK_ELSEWHERE, old_string="// the old launch", new_string="// the launch")
add("browser-keychain: an Edit elsewhere in a full-size file with an old bare launch is allowed", "allow",
    tool="Edit", file_path=BK_LARGE, old_string="// tail", new_string="// tail, edited")
