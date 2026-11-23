# section 43730
FAMILY = "browser-keychain"
# A spread of a constant is no literal list: the launch takes its switches from the constant, so both switches in the
# text pass it (decision render-browser-no-keychain: a launch whose args is a name or a spread passes when both
# switches appear anywhere in the same text). A literal list with no spread, and a spread with no switch anywhere in
# the text, are still refused. BK_DIR is the section 43728 constant (this file loads after it, in the same module).

BK_SPREAD_JS = ('const SW = ["--use-mock-keychain", "--password-store=basic"];\n'
                'const b = await chromium.launch({ args: [...SW, "--no-sandbox"] });\n')
BK_SPREAD_PY = ('SW = ["--use-mock-keychain", "--password-store=basic"]\n'
                'b = p.chromium.launch(args=[*SW, "--no-sandbox"])\n')

# ---- Passes: the switches sit in the constant the spread names.
add("browser-keychain: a JS spread of a constant with both switches, plus another flag, is allowed", "allow",
    tool="Write", file_path=os.path.join(BK_DIR, "spread.mjs"), content=BK_SPREAD_JS)
add("browser-keychain: a Python spread of a constant with both switches, plus another flag, is allowed", "allow",
    tool="Write", file_path=os.path.join(BK_DIR, "spread.py"), content=BK_SPREAD_PY)
sh("browser-keychain: a node -e spread of a constant with both switches is allowed",
   "node -e \"const SW = ['--use-mock-keychain', '--password-store=basic']; (async () => { "
   "await chromium.launch({ args: [...SW, '--no-sandbox'] }); })()\"", "allow", tool="Bash")

# ---- Refusals: a literal list with no spread and no switch, and a spread with no switch anywhere in the text.
add("browser-keychain: a literal args list with no spread and no switch is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "literal-bare.mjs"),
    content='const b = await chromium.launch({ args: ["--no-sandbox"] });\n', carries=BK_REMEDY)
add("browser-keychain: a Python literal args list with no spread and no switch is refused", "deny",
    "browser-keychain", tool="Write", file_path=os.path.join(BK_DIR, "literal-bare.py"),
    content='b = p.chromium.launch(args=["--no-sandbox"])\n', carries=BK_REMEDY)
add("browser-keychain: a spread with no switch anywhere in the text is refused", "deny", "browser-keychain",
    tool="Write", file_path=os.path.join(BK_DIR, "spread-bare.mjs"),
    content='const b = await chromium.launch({ args: [...EXTRA, "--no-sandbox"] });\n', carries=BK_REMEDY)
