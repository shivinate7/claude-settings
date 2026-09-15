# Wire %USERPROFILE%\.claude to the files in this clone (Windows local sessions).
#
#   Run once from the clone:   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# What it does:
#   ~\.claude\CLAUDE.md      -> one-line pointer: @C:/path/to/claude-settings/CLAUDE.md
#   ~\.claude\settings.json  -> symlink to <clone>\settings.json (needs Developer Mode or admin),
#                               falls back to a copy and tells you to re-run after each git pull.
$ErrorActionPreference = 'Stop'

$RepoDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }
New-Item -ItemType Directory -Force -Path $ClaudeDir | Out-Null

function Log([string]$msg) { Write-Host "claude-settings: $msg" }

# Bandaid for machines without symlink rights: a git post-merge hook in this clone re-copies
# settings.json into ~\.claude after every `git pull`, so pull stays the only update step.
function Install-PostMergeHook {
    $hooksDir = Join-Path $RepoDir '.git\hooks'
    if (-not (Test-Path $hooksDir)) { Log "no .git\hooks directory found; skipping post-merge hook"; return }
    $hookPath = Join-Path $hooksDir 'post-merge'
    $marker   = '# claude-settings post-merge hook'
    if ((Test-Path $hookPath) -and -not ((Get-Content -Raw $hookPath) -match [regex]::Escape($marker))) {
        Log "a post-merge hook already exists at $hookPath and is not ours; left untouched. Re-run install.ps1 after pulls instead."
        return
    }
    $hook = @"
#!/bin/sh
$marker
# Keeps ~/.claude/settings.json in sync after every git pull when symlinks are unavailable.
repo="`$(git rev-parse --show-toplevel)"
dest="`${CLAUDE_CONFIG_DIR:-`$HOME/.claude}/settings.json"
if [ -f "`$repo/settings.json" ] && [ ! -L "`$dest" ]; then
  cp "`$repo/settings.json" "`$dest" && echo "claude-settings: refreshed `$dest"
fi
exit 0
"@
    $hook = $hook -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText($hookPath, $hook, (New-Object System.Text.UTF8Encoding $false))
    Log "installed git post-merge hook; from now on 'git pull' also refreshes settings.json. No re-run needed."
}

# ---- CLAUDE.md pointer -------------------------------------------------------------------------
# Forward slashes: the @import parser is happier with them than with backslashes.
$Pointer  = '@' + (($RepoDir -replace '\\', '/').TrimEnd('/')) + '/CLAUDE.md'
$TargetMd = Join-Path $ClaudeDir 'CLAUDE.md'

if (Test-Path $TargetMd) {
    $existing = Get-Content -Raw $TargetMd
    if ($existing.Trim() -ne $Pointer) {
        $bak = "$TargetMd.bak.$(Get-Date -Format yyyyMMddHHmmss)"
        Copy-Item $TargetMd $bak
        Log "existing $TargetMd backed up to $bak; fold anything you want to keep into $RepoDir\CLAUDE.md"
    }
}
Set-Content -Path $TargetMd -Value $Pointer -Encoding UTF8 -NoNewline
Log "wrote $TargetMd -> $Pointer"

# ---- settings.json -----------------------------------------------------------------------------
$SrcJson    = Join-Path $RepoDir 'settings.json'
$TargetJson = Join-Path $ClaudeDir 'settings.json'

$item = Get-Item $TargetJson -ErrorAction SilentlyContinue
if ($item -and $item.LinkType -eq 'SymbolicLink' -and $item.Target -eq $SrcJson) {
    Log "$TargetJson already links to $SrcJson"
    exit 0
}

if ($item -and -not $item.LinkType) {
    $bak = "$TargetJson.bak.$(Get-Date -Format yyyyMMddHHmmss)"
    Move-Item $TargetJson $bak
    Log "existing $TargetJson moved to $bak; merge any keys you want (permissions, etc.) into $SrcJson"
} elseif ($item) {
    Remove-Item $TargetJson
}

try {
    New-Item -ItemType SymbolicLink -Path $TargetJson -Target $SrcJson -ErrorAction Stop | Out-Null
    Log "linked $TargetJson -> $SrcJson (git pull in the clone is now the whole update)"
} catch {
    Copy-Item $SrcJson $TargetJson
    Log "symlink not permitted (enable Windows Developer Mode, or run as admin); copied instead."
    Install-PostMergeHook
}
