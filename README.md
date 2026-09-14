# claude-settings

One source of truth for my user-level Claude Code config, read by local sessions and by cloud
sessions started from the desktop app / claude.ai/code.

| File            | Becomes                                              |
| --------------- | ---------------------------------------------------- |
| `CLAUDE.md`     | `~/.claude/CLAUDE.md` (via a one-line `@` import)    |
| `settings.json` | `~/.claude/settings.json` (symlink locally, generated copy in the cloud) |
| `install.sh`    | Wiring for Linux/macOS and for the cloud setup script |
| `install.ps1`   | Wiring for Windows                                   |

`settings.json` sets `outputStyle: "Concise"` (built-in style, needs Claude Code v2.1.237+) and
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`.

## Local machine (Windows)

```powershell
git clone https://github.com/ssemwal-cdc/claude-settings C:\src\claude-settings
cd C:\src\claude-settings
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Result:

* `~\.claude\CLAUDE.md` contains one line, `@C:/src/claude-settings/CLAUDE.md`. Claude Code
  resolves `@` imports at session start, so after `git pull` the next session reads the new file.
  Nothing to re-run.
* `~\.claude\settings.json` is a symlink to the clone's `settings.json`. Symlinks need Windows
  Developer Mode (Settings > System > For developers) or an admin shell. Without it the script
  copies the file instead and you re-run `install.ps1` after each pull.
* Any existing `~\.claude\CLAUDE.md` or `settings.json` is backed up as `*.bak.<timestamp>`
  first. Merge keys you want to keep (for example a `permissions.allow` list Claude Code built up
  from "always allow") into the repo's `settings.json`, then commit.

Verify in a session: `/context` lists `~/.claude/CLAUDE.md` and the imported file under
**Memory files**; `/status` shows the Concise output style.

Linux/macOS: `bash install.sh` from the clone does the same with a real symlink.

## Cloud sessions (desktop app, claude.ai/code, `claude --cloud`)

Cloud VMs never see your machine's `~/.claude`, so the environment's **setup script** has to
recreate it. In claude.ai/code > environment settings, set the setup script to:

```bash
curl -fsSL https://raw.githubusercontent.com/ssemwal-cdc/claude-settings/main/install.sh | bash -s -- --cloud
```

Leave network access at **Trusted** (or add `raw.githubusercontent.com` to a Custom list).
This runs as root before Claude starts and writes:

* `/root/.claude/CLAUDE.md` = `@~/claude-settings/CLAUDE.md`
* `/root/.claude/settings.json` = repo `settings.json` plus a `SessionStart` hook that re-runs
  the same one-liner, so each new or resumed session re-fetches both files.

Why the hook: Anthropic snapshots the VM after the setup script and reuses it for ~7 days, so the
setup script alone would pin whatever was on `main` at snapshot time. The hook keeps it fresh.
The hook runs after Claude launches, so a change pushed minutes ago may land one session late.
Editing the setup script text (any character) forces a fresh snapshot immediately.

Pin a commit instead of `main` if you want cloud sessions to change only when you say so:
replace `/main/` in the URL with `/<sha>/` and set `CLAUDE_SETTINGS_REF=<sha>` as an environment
variable on the environment.

Verify in a cloud session: `/context` for the memory file, and ask Claude to run
`echo $CLAUDE_CODE_SUBAGENT_MODEL` (expect `sonnet`).

## Editing

Edit `CLAUDE.md` or `settings.json` here, commit, push. Local picks it up on `git pull`; cloud
picks it up on the next session start.

Keep hooks out of `settings.json`: the cloud install generates its own, and a hook written for
bash would error in a Windows local session.
