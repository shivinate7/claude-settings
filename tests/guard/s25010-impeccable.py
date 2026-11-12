# section 25010
FAMILY = "impeccable"
FAMILIES["impeccable"] = "impeccable is review-only"
#
# Owner ruling, 2026-10-10, decisions/design-skills.md: the impeccable plugin loads only for review
# (audit, critique). Its build commands and its settings writers are refused. Other skills pass.

IMP = "impeccable:impeccable"

add("impeccable: audit is allowed", "allow", tool="Skill", skill=IMP, args="audit")
add("impeccable: audit with a folder is allowed", "allow", tool="Skill", skill=IMP,
    args="audit src/pages")
add("impeccable: critique is allowed", "allow", tool="Skill", skill=IMP, args="critique")
add("impeccable: critique with a folder is allowed", "allow", tool="Skill", skill=IMP,
    args="critique app/")
add("impeccable: bare name with audit is allowed", "allow", tool="Skill", skill="impeccable",
    args="audit")

add("impeccable: no args is denied", "deny", "impeccable-review-only", tool="Skill", skill=IMP)
add("impeccable: polish is denied", "deny", "impeccable-review-only", tool="Skill", skill=IMP,
    args="polish")
add("impeccable: audit then polish in one args string is denied", "deny", "impeccable-review-only",
    tool="Skill", skill=IMP, args="audit; polish")
add("impeccable: bare name with polish is denied", "deny", "impeccable-review-only", tool="Skill",
    skill="impeccable", args="polish")
# refusal-vs-rule (impeccable-review-only, design-skills): the skill reads the FIRST word as its command
# and the rest as target text. A `;` inside that target starts no second command, so a review with a
# focus after the `;` loads. A non-review first word stays refused. A non-review verb after the `;` also
# stays refused: the skill asks once when two commands fit, and the guard cannot tell that ask from a run.
add("impeccable: audit with a focus after a semicolon is allowed", "allow", tool="Skill", skill=IMP,
    args="audit the page; focus on a11y")
add("impeccable: critique with a focus after a semicolon is allowed", "allow", tool="Skill", skill=IMP,
    args="critique the page; focus on contrast")
add("impeccable: audit then polish after the semicolon is denied", "deny", "impeccable-review-only",
    tool="Skill", skill=IMP, args="audit the page; then polish")
add("impeccable: audit then polish with no then after the semicolon is denied", "deny",
    "impeccable-review-only", tool="Skill", skill=IMP, args="audit the page; polish")
add("impeccable: a focus first word with an audit after the semicolon is denied", "deny",
    "impeccable-review-only", tool="Skill", skill=IMP, args="focus the page on a11y; audit")
add("impeccable: shape with a review target is denied", "deny", "impeccable-review-only", tool="Skill",
    skill=IMP, args="shape the page; audit")
# After a `;`, a part is a second command only when it opens with a command verb. The verbs are the
# Commands table of the skill itself, read here so this file holds no copy of the list. A word that is
# no command verb, such as `check`, is target text and passes.
def impeccable_command_verbs():
    """The command verbs in the Commands table of skills/impeccable/SKILL.md, in table order."""
    with open(os.path.join(REPO, "skills", "impeccable", "SKILL.md"), encoding="utf-8") as fh:
        table = fh.read()
    verbs = re.findall(r"^\| `([a-z]+)[^`]*` \| (?:Build|Evaluate|Refine|Enhance|Fix|Iterate) \|",
                       table, re.M)
    if "polish" not in verbs or "animate" not in verbs or len(verbs) < 20:
        sys.exit("impeccable verbs: the Commands table of the skill did not parse (%d verbs)" % len(verbs))
    return verbs


add("impeccable: audit with a check after the semicolon is allowed", "allow", tool="Skill", skill=IMP,
    args="audit the header; check the contrast on mobile")
add("impeccable: audit then polish with no target after the semicolon is denied", "deny",
    "impeccable-review-only", tool="Skill", skill=IMP, args="audit; polish")
add("impeccable: critique then animate after the semicolon is denied", "deny",
    "impeccable-review-only", tool="Skill", skill=IMP, args="critique; animate the hero")
for _verb in impeccable_command_verbs():
    if _verb in ("audit", "critique"):   # the two reviews, which a `;` may follow
        continue
    add("impeccable: audit then a %s command verb after the semicolon is denied" % _verb, "deny",
        "impeccable-review-only", tool="Skill", skill=IMP, args="audit the page; %s the page" % _verb)

add("skill: frontend-design with args is allowed", "allow", tool="Skill", skill="frontend-design",
    args="polish")
add("skill: frontend-design with no args is allowed", "allow", tool="Skill",
    skill="frontend-design")

sh("impeccable bash: hooks on writes agent settings", "npx impeccable hooks on", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: hooks by script path is denied",
   "node \"$HOME/.claude/plugins/impeccable/scripts/impeccable.mjs\" hooks on", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: detect on folders is allowed", "npx impeccable detect src/pages app", "allow",
   cwd=NOGIT)


# impeccable, round two (owner ruling 2026-10-10, decisions/design-skills.md): the plugin is not
# installed. Its skill folder is pinned at skill-v4.8.0. Every Bash form below reaches the plugin's
# build or settings commands, through a version pin, a runner flag or a different subcommand.

sh("impeccable bash: a version-pinned hooks on is denied", "npx impeccable@4.5.2 hooks on", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: npx -y latest hooks on is denied", "npx -y impeccable@latest hooks on", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: npx -p latest hooks on is denied",
   "npx -p impeccable@latest impeccable hooks on", "deny", "impeccable-review-only", cwd=NOGIT)

sh("impeccable bash: hooks status is allowed", "npx impeccable hooks status", "allow", cwd=NOGIT)
sh("impeccable bash: detect on a folder is allowed", "npx impeccable detect src", "allow",
   cwd=NOGIT)

add("impeccable skill: critique with a trailing newline is allowed", "allow", tool="Skill",
    skill="impeccable:impeccable", args="critique\n")
add("impeccable skill: a leading slash on the name is denied", "deny", "impeccable-review-only",
    tool="Skill", skill="/impeccable", args="polish")


# impeccable, round three: the shell rule is an ALLOW list. Only `detect ...` and `hooks status`
# pass; every other subcommand is denied, including any a later release adds. Shell wrappers
# (bash -c, sh -c, npx -c, npx.cmd, PowerShell's call operator) reach the same rule.

sh("impeccable bash: npx -c install is denied", "npx -c 'impeccable install'", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: npx.cmd install is denied", "npx.cmd impeccable install", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: bash -c install is denied", "bash -c 'npx impeccable install'", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: sh -c pin is denied", "sh -c \"impeccable pin x\"", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable powershell: call operator on the cmd shim install is denied",
   "& \"C:\\x\\impeccable.cmd\" install", "deny", "impeccable-review-only", tool="PowerShell",
   cwd=NOGIT)
sh("impeccable powershell: call operator on bash.exe -c install is denied",
   "& \"C:\\Program Files\\Git\\bin\\bash.exe\" -c \"impeccable install\"", "deny",
   "impeccable-review-only", tool="PowerShell", cwd=NOGIT)
sh("impeccable powershell: call operator on bash -c install is denied",
   "& bash -c \"impeccable install\"", "deny", "impeccable-review-only", tool="PowerShell",
   cwd=NOGIT)
sh("impeccable powershell: an assignment around the call operator is denied",
   "$r = & impeccable install", "deny", "impeccable-review-only", tool="PowerShell", cwd=NOGIT)
sh("impeccable powershell: a script block around the call operator is denied",
   "{ & impeccable install }", "deny", "impeccable-review-only", tool="PowerShell", cwd=NOGIT)
sh("impeccable bash: a subcommand not yet named is denied", "npx impeccable some-future-cmd",
   "deny", "impeccable-review-only", cwd=NOGIT)

sh("impeccable bash: bash -c detect is allowed", "bash -c 'npx impeccable detect src'", "allow",
   cwd=NOGIT)
sh("impeccable bash: the pinned script path, detect, is allowed",
   "skills/impeccable/scripts/impeccable detect src", "allow", cwd=NOGIT)

# impeccable, detect after leading flags or a `--` separator. The subcommand is the first word after the
# flags and the `--` that ends them, so a `detect` there is the same read-only call; `npm run <script> --
# <args>` hands the `--` on to the script. The flags and the separator never let a build or a settings
# writer through: the word after them must still be `detect`, and a `detect` later in the call is no subcommand.
sh("impeccable bash: detect after a leading json flag is allowed",
   "impeccable --json detect", "allow", cwd=NOGIT)
sh("impeccable bash: detect after a leading json flag through npx is allowed",
   "npx impeccable --json detect", "allow", cwd=NOGIT)
sh("impeccable bash: detect after two leading flags is allowed",
   "impeccable --json --verbose detect", "allow", cwd=NOGIT)
sh("impeccable bash: detect after a -- separator is allowed",
   "impeccable -- detect", "allow", cwd=NOGIT)
sh("impeccable bash: detect after a -- separator under npm run is allowed",
   "npm run impeccable -- detect", "allow", cwd=NOGIT)

sh("impeccable bash: live-server behind a leading json flag is denied",
   "impeccable --json live-server", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: live-server after a -- separator under npm run is denied",
   "npm run impeccable -- live-server", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: context behind a leading json flag is denied",
   "impeccable --json context", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: polish after a -- separator is denied",
   "impeccable -- polish", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: a settings writer behind a leading flag is denied",
   "npx impeccable --json hooks on", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: flags with no subcommand are denied",
   "impeccable --json", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: a detect after a live-server subcommand is denied",
   "impeccable live-server detect", "deny", "impeccable-review-only", cwd=NOGIT)
# Both chains stay refused. The plain one is denied by its second segment alone, so a fix that reads
# only the first segment fails it. The flag-led one is denied today by its first segment; it holds once
# the flag fix lands.
sh("impeccable bash: a detect chained before a live-server is denied",
   "impeccable detect; impeccable live-server", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: a flag-led detect chained before a live-server is denied",
   "impeccable --json detect; impeccable live-server", "deny", "impeccable-review-only", cwd=NOGIT)


# impeccable, heredoc bodies. A heredoc body is text, not a run, so the shell reader must not read a
# body line as a command. A body is KEPT (judged as shell) when an interpreter word sits on the header
# line, or when a lone quote hides the header; then a body line that starts with the bare word is denied.
# A PowerShell here-string ends its quote at the first apostrophe, so the rest of the body is read as shell.
# A case name ending (red) marks a verdict the rule once got wrong; (green) marks an allow it got right.

# Text that names the word is allowed, in a body the guard keeps.
sh("impeccable heredoc: a python heredoc line naming the word is allowed (red)",
   "python3 - <<'EOF'\nfor f in files:\n    if 'impeccable' in f: continue\nEOF", "allow",
   cwd=NOGIT)
sh("impeccable heredoc: a body file named after an interpreter word is allowed (red)",
   "cat > node-notes.md <<'EOF'\nimpeccable audit of the page looks fine\nEOF", "allow",
   cwd=NOGIT)
sh("impeccable heredoc: a backtick span across lines in a kept body is allowed (red)",
   "cat > node-body.md <<'EOF'\n`multi\nimpeccable audit\ntemplate`\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a pr body under a node title is allowed (red)",
   "gh pr create --draft --title \"node 20 bump\" --body-file - <<'EOF'\n"
   "impeccable critique ran on the page\nEOF", "allow", cwd=NOGIT)
sh("impeccable powershell: a here-string with an apostrophe is allowed (red)",
   "$body = @'\nDon't ship this.\nimpeccable audit ran on the page.\n'@", "allow",
   tool="PowerShell", cwd=NOGIT)

# A body that runs install is denied. An unquoted heredoc runs $(...) and backticks in its body,
# and an expandable here-string runs $(...).
sh("impeccable heredoc: an unquoted body that runs install by substitution is denied (red)",
   "cat > body.md <<EOF\n$(npx impeccable install)\nEOF", "deny", "impeccable-review-only",
   cwd=NOGIT)
sh("impeccable heredoc: an unquoted body that runs install by backtick is denied (red)",
   "cat > body.md <<EOF\n`npx impeccable install`\nEOF", "deny", "impeccable-review-only",
   cwd=NOGIT)
sh("impeccable powershell: an expandable here-string that runs install is denied (red)",
   "$b = @\"\n$(npx impeccable install)\n\"@", "deny", "impeccable-review-only",
   tool="PowerShell", cwd=NOGIT)

# KEEP: a shell that runs the body still reads it, and a hash inside a quoted string is not a comment.
sh("impeccable heredoc: bash runs a body that names install is denied",
   "bash <<'EOF'\nnpx impeccable install\nEOF", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable heredoc: sh -s runs a body that names polish is denied",
   "sh -s <<EOF\nimpeccable polish src\nEOF", "deny", "impeccable-review-only", cwd=NOGIT)
sh("impeccable bash: a hash inside a quoted echo does not hide a later install",
   "echo \"# not a comment\" && npx impeccable install", "deny", "impeccable-review-only",
   cwd=NOGIT)

# Text that names the word, in a body or a string the guard reads as text, is allowed.
sh("impeccable heredoc: a commit message body starting with the word is allowed",
   "git commit -F - <<'EOF'\nfeat: note\n\nimpeccable audit ran on the page; no UI change.\nEOF",
   "allow", cwd=NOGIT)
sh("impeccable heredoc: a cat body file that mentions the word is allowed",
   "cat > body.md <<'EOF'\n# PR\n\nRan impeccable audit on the page.\nEOF", "allow", cwd=NOGIT)
sh("impeccable echo: a double-quoted string naming the word is allowed",
   "echo \"impeccable is review-only\"", "allow", cwd=NOGIT)
sh("impeccable echo: a single-quoted string naming the word is allowed",
   "echo 'impeccable audit ran'", "allow", cwd=NOGIT)
sh("impeccable echo: a double-quoted line comment opener is text",
   "echo \"// impeccable audit\"", "allow", cwd=NOGIT)
sh("impeccable echo: a double-quoted block comment opener is text",
   "echo \"/* impeccable */\"", "allow", cwd=NOGIT)
sh("impeccable echo: a multi-line double-quoted string naming install is allowed",
   "echo \"start\nimpeccable install\nend\"", "allow", cwd=NOGIT)
sh("impeccable heredoc: a hash opener on a kept body line is a comment",
   "cat > node-body.md <<'EOF'\n# impeccable audit\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a double-slash opener on a kept body line is text",
   "cat > node-body.md <<'EOF'\n// impeccable audit\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a block opener on a kept body line is text",
   "cat > node-body.md <<'EOF'\n/* impeccable */\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a lone apostrophe in a kept body is allowed",
   "cat > node-body.md <<'EOF'\nimpeccable audit: it's fine\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a lone apostrophe in a plain body is allowed",
   "cat > body.md <<'EOF'\nimpeccable audit: it's fine\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a multi-line backtick span in a plain body is allowed",
   "cat > body.md <<'EOF'\n`multi\nimpeccable audit\ntemplate`\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a quoted delimiter keeps backticks literal",
   "cat > body.md <<'EOF'\n`npx impeccable install`\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a quoted delimiter keeps substitution literal",
   "cat > body.md <<'EOF'\n$(npx impeccable install)\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: an unquoted body with plain text is allowed",
   "cat > body.md <<EOF\nimpeccable audit ran\nEOF", "allow", cwd=NOGIT)
sh("impeccable powershell: a plain here-string naming the word is allowed",
   "$body = @'\nimpeccable audit ran on the page.\n'@", "allow", tool="PowerShell", cwd=NOGIT)
sh("impeccable powershell: a hash opener inside a here-string is text",
   "$body = @'\n# impeccable audit\n'@", "allow", tool="PowerShell", cwd=NOGIT)

# impeccable, heredoc bodies. Each body names
# `npx impeccable install`, and each command runs that body: a quoted shell word behind a wrapper
# flag (`sudo -b "bash"`), behind a message-flag pattern that swallows it (`tool --run-m "sh"`,
# `ssh -t "bash -s"`), a script a heredoc writes and `bash` runs by name, and `pwsh`.

# The run hides behind a wrapper, a message-flag value, a written script, or pwsh.
sh("impeccable heredoc: a sudo flag before a quoted bash word runs the body is denied (red)",
   "sudo -b \"bash\" <<'EOF'\nnpx impeccable install\nEOF", "deny", "impeccable-review-only",
   cwd=NOGIT)
sh("impeccable heredoc: a run-m flag before a quoted sh word runs the body is denied (red)",
   "tool --run-m \"sh\" <<'EOF'\nnpx impeccable install\nEOF", "deny", "impeccable-review-only",
   cwd=NOGIT)
sh("impeccable heredoc: an ssh tty flag before a quoted bash -s word runs the body is denied (red)",
   "ssh -t \"bash -s\" <<'EOF'\nnpx impeccable install\nEOF", "deny", "impeccable-review-only",
   cwd=NOGIT)
sh("impeccable heredoc: a run.sh written by heredoc and run by bash is denied (red)",
   "cat > run.sh <<'EOF'\nnpx impeccable install\nEOF\nbash run.sh", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable heredoc: a run.bash written by heredoc and run by bash is denied (red)",
   "cat > run.bash <<'EOF'\nnpx impeccable install\nEOF\nbash run.bash", "deny",
   "impeccable-review-only", cwd=NOGIT)
sh("impeccable heredoc: a pwsh body that names install is denied (red)",
   "pwsh <<'EOF'\nnpx impeccable install\nEOF", "deny", "impeccable-review-only", cwd=NOGIT)

# A message body or a file body that names install is text, so it stays an allow.
sh("impeccable heredoc: a git commit body that names install is allowed (green)",
   "git commit -F - <<'EOF'\nfeat: note\n\nnpx impeccable install is not run here.\nEOF",
   "allow", cwd=NOGIT)
sh("impeccable heredoc: a gh pr body that names install is allowed (green)",
   "gh pr create --draft --title \"impeccable note\" --body-file - <<'EOF'\n"
   "npx impeccable install is not run here.\nEOF", "allow", cwd=NOGIT)
sh("impeccable heredoc: a node-notes.md body that names install is allowed (green)",
   "cat > node-notes.md <<'EOF'\nnpx impeccable install is not run here.\nEOF", "allow",
   cwd=NOGIT)


def impeccable_settings_case():
    """settings.json names no impeccable plugin or marketplace. The skill folder is the install."""
    with open(os.path.join(REPO, "settings.json"), encoding="utf-8") as handle:
        settings = json.load(handle)
    named = [key for key in settings.get("enabledPlugins", {}) if "impeccable" in key]
    named += [key for key in settings.get("extraKnownMarketplaces", {}) if "impeccable" in key]
    if named:
        return False, "settings.json still names: " + ", ".join(named)
    return True, "no impeccable plugin or marketplace in settings.json"


LOG_CHECKS_EXTRA.append(("impeccable: settings.json names no impeccable plugin",
                         impeccable_settings_case))


def run_folder_sweep_case():
    """test-temp-standard: the sweep removes a sibling run folder over a day old and keeps a new one."""
    fake = os.path.join(ROOT, "sweep-root")   # a temp root of its own, inside this run's folder
    old = os.path.join(fake, "4242-" + "a" * 32)
    new = os.path.join(fake, "4243-" + "b" * 32)
    for path in (old, new):
        os.makedirs(path)
    stale = time.time() - RUN_FOLDER_MAX_AGE - 3600
    os.utime(old, (stale, stale))
    sweep_run_folders(fake, own=ROOT)
    if os.path.exists(old):
        return False, "the old sibling run folder stays"
    if not os.path.isdir(new):
        return False, "the new sibling run folder was removed"
    return True, "the old sibling run folder goes, the new one stays"


FIXTURELESS_CHECKS.add(run_folder_sweep_case)
LOG_CHECKS_EXTRA.append(("temp: the sweep removes an old sibling run folder and keeps a new one",
                         run_folder_sweep_case))


# --------------------------------------------------------------------------- git_reads.branch_is_ancestor: the registration
# The four cases are defined in the branch-worktree section, where they belong. LOG_CHECKS_EXTRA is made further down,
# so the cases register here, with the family that section names.
