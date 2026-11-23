# A test browser never asks for the owner's keychain

## The question

How does a lane agent render a mockup or a page without a macOS dialog that asks for the owner's keychain password?

## The ruling

Two parts. Neither is an owner ruling yet: both came from the incident below, and the owner may change either.

1. The shared tool is `bin/shoot` (decision `shoot-is-one-shared-command`). Its single-target mode, `shoot --file HTML` or `shoot --url URL`, takes one PNG of one page with no config. `shoot` launches Chromium with `--use-mock-keychain` and `--password-store=basic`, and so does `skills/waiting-page/check_designs.mjs`. A mockup is looked at in the built-in browser pane or with `shoot`, never with a bare browser launch (`agents/designer.md`, skill `design-explore`).
2. Guard rule `browser-keychain` in `hooks/guard_browser.py` refuses a launch that lacks either switch:
   - A Bash or PowerShell command that holds a script which calls `chromium.launch(`, `chromium.launchPersistentContext(`, `launch_persistent_context(` or `puppeteer.launch(`. The script is an interpreter's inline text (`node -e`, `python3 -c`, `bash -c`), a heredoc fed to an interpreter, or a script file the command writes (`cat > a.mjs <<EOF`, `echo ... > a.py`).
   - A Bash command that runs the Playwright CLI for Chromium (`playwright screenshot`, `pdf`, `open`, `codegen`, `cr`; `-b firefox` or `-b webkit` passes) or `@puppeteer/browsers launch`. The CLI takes no Chromium switch, so it is always refused.
   - A Bash command that runs a Chromium or Chrome binary (Chrome for Testing, Playwright's cached build, a system Chromium) with no both switches. `--version` and `--help` pass.
   - A Write, Edit or MultiEdit of a script file (`.js .mjs .cjs .jsx .ts .mts .cts .tsx .py .sh`, or a file with no extension that starts with a shebang). The rule judges the launches the write adds: text the file held before, spelled the same, is no addition, so an edit elsewhere in a file passes, and so does an edit that adds the switches.
   - A launch whose `args` is a name or a spread passes when both switches appear anywhere else in the same text.
   - The scan blanks comments and string contents before it looks for a call, so `grep 'chromium.launch('`, an `echo`, a commit message and a commented-out call pass. The switches are read in the strings.
   - The rule runs on every host. The switches do nothing harmful off macOS.

The remedy names both switches and `shoot`. It does not name any other launch route.

Outcome protected: the owner's stored secrets. Choosing Allow in the dialog gives a test browser the keychain's "Chromium Safe Storage" key.

## The incident

Owner gripe "Test browser asked for the owner's keychain password" (2026-11-21, session degen). A lane agent launched a Playwright or Puppeteer Chromium ("Google Chrome for Testing") to render mockups on macOS, and a dialog asked for the owner's keychain password for "Chromium Safe Storage".

Unmeasured: that a bare launch always raises the dialog (a headless build may not), and that the two switches stop it on every Chromium build. The switches are Chromium's own documented ones.

## Named limits

- A script file that the command only runs (`node look.mjs`) is not read. The Write or Edit that made it was judged. A script written by a tool the guard does not judge is not.
- A launch through a binding the scan cannot name (`const b = pw.chromium; b.launch()`, `pw['chromium'].launch()`), Selenium, and a launch in an `-e` script of a form it does not tokenize (`(await import('puppeteer')).launch()`) are not seen.
- A regex literal that holds a quote can hide a launch on the same line from the scan. A lone apostrophe in JSX text spoils that line only.
- A launch whose `args` is a name passes when both switches appear anywhere in the text, even if the named list is another one.
- Existing launches with no switches stay in the test files (`lint/test_shoot.mjs`, the page tests) and in `docs/plans/3d-browser-dummy/check.mjs`. They are not edited here and the rule does not refuse a write that leaves them as they are.

Kind: process
Home: hooks/guard_browser.py
