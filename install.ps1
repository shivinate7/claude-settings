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
    Log "re-run install.ps1 after each git pull to refresh settings.json. CLAUDE.md needs no re-run."
}
