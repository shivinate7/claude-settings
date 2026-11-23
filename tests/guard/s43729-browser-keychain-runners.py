# section 43729
FAMILY = "browser-keychain"
# Forms rule browser-keychain must read (decision render-browser-no-keychain, hooks/guard_browser.py): a Python `-m`
# run of the Playwright CLI, a package runner that starts an interpreter (npx tsx, pnpm exec node, uv run python), a
# launch whose args come through a name or an options object, and a Python comment. A refusal here is red on a rule
# that does not read its form. A pass is a control: a rule that already passed it must keep passing it.
# BK_REMEDY and BK_DIR are the section 43728 constants (this file loads after it, in the same module).

BK_NODE_BARE = ("import { chromium } from 'playwright'; (async () => { const b = await chromium.launch(); "
                "await b.close(); })()")
BK_NODE_FLAGGED = ("import { chromium } from 'playwright'; (async () => { await chromium.launch({ "
                   "args: ['--use-mock-keychain', '--password-store=basic'] }); })()")
BK_PY_BARE = "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch()"

# ---- F2: the Playwright CLI run as a Python module, and the Python package runner.
sh("browser-keychain: python3 -m playwright screenshot with no switch is refused",
   "python3 -m playwright screenshot --browser chromium https://example.com shot.png",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: python3 -m playwright open is refused, the CLI takes no switch",
   "python3 -m playwright open https://example.com", "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: python3 -m playwright screenshot with -b firefox is allowed",
   "python3 -m playwright screenshot -b firefox https://example.com shot.png", "allow", tool="Bash")
sh("browser-keychain: python3 -m pytest is allowed", "python3 -m pytest -q tests/", "allow", tool="Bash")

# ---- F3: a package runner that starts an interpreter, each with a bare launch, refused. The flagged launch and
# `npm run build` pass.
sh("browser-keychain: npx tsx -e with a bare launch is refused", "npx tsx -e \"" + BK_NODE_BARE + "\"",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: npx ts-node -e with a bare launch is refused", "npx ts-node -e \"" + BK_NODE_BARE + "\"",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: pnpm exec node -e with a bare launch is refused", "pnpm exec node -e \"" + BK_NODE_BARE + "\"",
   "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: npx -p playwright node -e with a bare launch is refused",
   "npx -p playwright node -e \"" + BK_NODE_BARE + "\"", "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: an npx tsx heredoc with a bare launch is refused",
   "npx tsx <<'EOF'\n" + BK_NODE_BARE + "\nEOF", "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: uv run python -c with a bare launch is refused",
   "uv run python -c \"" + BK_PY_BARE + "\"", "deny", "browser-keychain", carries=BK_REMEDY)
sh("browser-keychain: npx tsx -e with both switches is allowed", "npx tsx -e \"" + BK_NODE_FLAGGED + "\"",
   "allow", tool="Bash")
sh("browser-keychain: npm run build is allowed", "npm run build", "allow", tool="Bash")

# ---- F4: the launch's args come through a name, an options object or a spread. The switches must be in the text
# the call reads, and a literal args list must carry them.
add("browser-keychain: a launch with an options object that holds both switches is allowed", "allow",
    tool="Write", file_path=os.path.join(BK_DIR, "opts.mjs"),
    content='const opts = { args: ["--use-mock-keychain", "--password-store=basic"] };\nconst b = await chromium.launch(opts);\n')
add("browser-keychain: a Python launch(**opts) with both switches in opts is allowed", "allow",
    tool="Write", file_path=os.path.join(BK_DIR, "opts.py"),
    content='OPTS = dict(args=["--use-mock-keychain", "--password-store=basic"])\nb = p.chromium.launch(**OPTS)\n')
add("browser-keychain: a launch(opts) with no switch anywhere in the text is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "opts-bare.mjs"),
    content="const opts = { headless: true };\nconst b = await chromium.launch(opts);\n", carries=BK_REMEDY)
add("browser-keychain: an empty launch() with the switches elsewhere in the text is refused", "deny",
    "browser-keychain", tool="Write", file_path=os.path.join(BK_DIR, "empty-call.mjs"),
    content='const opts = { args: ["--use-mock-keychain", "--password-store=basic"] };\nconst b = await chromium.launch();\n',
    carries=BK_REMEDY)
add("browser-keychain: a literal args list with no switch is refused, though the switches sit elsewhere", "deny",
    "browser-keychain", tool="Write", file_path=os.path.join(BK_DIR, "args-other.mjs"),
    content='const opts = { args: ["--use-mock-keychain", "--password-store=basic"] };\n'
            'const b = await chromium.launch({ args: ["--no-sandbox"] });\n', carries=BK_REMEDY)

# ---- F5: Python comments. A `#` in a string is no comment: the launch after it is live.
add("browser-keychain: a Python comment that names a bare launch is allowed", "allow", tool="Write",
    file_path=os.path.join(BK_DIR, "comment.py"), content="# b = p.chromium.launch()\nprint('ok')\n")
add("browser-keychain: a # inside a Python string does not hide a bare launch after it", "deny",
    "browser-keychain", tool="Write", file_path=os.path.join(BK_DIR, "hash.py"),
    content='url = "http://x/#a"\nb = p.chromium.launch()\n', carries=BK_REMEDY)
