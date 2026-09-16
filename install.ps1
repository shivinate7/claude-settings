# Wire %USERPROFILE%\.claude to the files in this clone (Windows local sessions).
#
#   Run once from the clone:   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# What it does:
#   ~\.claude\CLAUDE.md      -> one-line pointer: @C:/path/to/claude-settings/CLAUDE.md
#   ~\.claude\agents\*.md    -> role definitions (builder, reviewer), symlink per file
#   ~\.claude\lint\*         -> STE linter + hook gate (needs python3 on PATH), symlink per file
#   ~\.claude\settings.json  -> symlink to <clone>\settings.json (needs Developer Mode or admin),
#                               falls back to a copy plus a git post-merge hook that re-copies
#                               settings.json, agents\*.md, and lint\* after each git pull.
$ErrorActionPreference = 'Stop'

$RepoDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }
New-Item -ItemType Directory -Force -Path $ClaudeDir | Out-Null

function Log([string]$msg) { Write-Host "claude-settings: $msg" }

# One dated line per install.ps1 run, on every exit path, so a copy-mode machine has a record
# of what happened without re-reading Write-Host output.
$InstallLogPath = Join-Path $ClaudeDir 'claude-settings-install.log'
function Write-InstallLog([string]$SettingsMode, [string]$AgentsMode, [string]$HookMode) {
    $line = "$(Get-Date -Format s) install.ps1: settings.json=$SettingsMode agents/lint=$AgentsMode hook=$HookMode`n"
    [System.IO.File]::AppendAllText($InstallLogPath, $line, (New-Object System.Text.UTF8Encoding $false))
}

# Bandaid for machines without symlink rights: a git post-merge hook in this clone re-copies
# settings.json into ~\.claude after every `git pull`, so pull stays the only update step.
# Returns 'installed' or 'skipped', for the install-log summary.
function Install-PostMergeHook {
    $hooksDir = Join-Path $RepoDir '.git\hooks'
    if (-not (Test-Path $hooksDir)) { Log "no .git\hooks directory found; skipping post-merge hook"; return 'skipped' }
    $hookPath = Join-Path $hooksDir 'post-merge'
    $marker   = '# claude-settings post-merge hook'
    if ((Test-Path $hookPath) -and -not ((Get-Content -Raw $hookPath) -match [regex]::Escape($marker))) {
        Log "a post-merge hook already exists at $hookPath and is not ours; left untouched. Re-run install.ps1 after pulls instead."
        return 'skipped'
    }
    $hook = @"
#!/bin/sh
$marker
# Keeps ~/.claude/settings.json, ~/.claude/agents/*, and ~/.claude/lint/* in sync after every
# git pull when symlinks are unavailable. Re-runs install.ps1 when the pull changed it, so a
# changed installer or hook body still lands without a manual re-run.
repo="`$(git rev-parse --show-toplevel)"
cfg="`${CLAUDE_CONFIG_DIR:-`$HOME/.claude}"
log="`$cfg/claude-settings-install.log"
if git rev-parse -q --verify ORIG_HEAD >/dev/null 2>&1 \
   && git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD | grep -qx 'install.ps1'; then
  mkdir -p "`$cfg"
  echo "`$(date) post-merge: install.ps1 changed, re-running install.ps1" >> "`$log"
  exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "`$repo/install.ps1"
fi
dest="`$cfg/settings.json"
if [ -f "`$repo/settings.json" ] && [ ! -L "`$dest" ]; then
  cp "`$repo/settings.json" "`$dest" && echo "claude-settings: refreshed `$dest"
fi
for sub in agents lint; do
  [ -d "`$repo/`$sub" ] || continue
  mkdir -p "`$cfg/`$sub"
  for f in "`$repo/`$sub"/*; do
    [ -f "`$f" ] || continue
    d="`$cfg/`$sub/`$(basename "`$f")"
    [ -L "`$d" ] || { cp "`$f" "`$d" && echo "claude-settings: refreshed `$d"; }
  done
done
exit 0
"@
    $hook = $hook -replace "`r`n", "`n"
    $tmpPath = Join-Path $hooksDir 'post-merge.tmp'
    [System.IO.File]::WriteAllText($tmpPath, $hook, (New-Object System.Text.UTF8Encoding $false))
    Move-Item -Force $tmpPath $hookPath
    Log "installed git post-merge hook; 'git pull' now refreshes settings.json, agents, and lint, and reruns install.ps1 when it changed."
    return 'installed'
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

# ---- agents\ and lint\ : per-file symlinks, copy fallback -----------------------------------------
$AgentCopied = $false
foreach ($sub in @('agents', 'lint')) {
    $srcDir  = Join-Path $RepoDir $sub
    $destDir = Join-Path $ClaudeDir $sub
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    foreach ($src in @(Get-ChildItem -Path $srcDir -File -ErrorAction SilentlyContinue)) {
        $dest = Join-Path $destDir $src.Name
        $cur  = Get-Item $dest -ErrorAction SilentlyContinue
        if ($cur -and $cur.LinkType -eq 'SymbolicLink' -and $cur.Target -eq $src.FullName) { continue }
        if ($cur -and -not $cur.LinkType) {
            if ((Get-FileHash $dest).Hash -ne (Get-FileHash $src.FullName).Hash) {
                $bak = "$dest.bak.$(Get-Date -Format yyyyMMddHHmmss)"
                Copy-Item $dest $bak
                Log "existing $dest backed up to $bak"
            }
            Remove-Item $dest
        } elseif ($cur) {
            Remove-Item $dest
        }
        try {
            New-Item -ItemType SymbolicLink -Path $dest -Target $src.FullName -ErrorAction Stop | Out-Null
            Log "linked $dest -> $($src.FullName)"
        } catch {
            Copy-Item $src.FullName $dest
            $AgentCopied = $true
            Log "copied $dest (symlink not permitted)"
        }
    }
}
if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    Log "python3 not found on PATH; the STE lint gate stays silent on this machine until Python is installed"
}

# ---- settings.json -----------------------------------------------------------------------------
$SrcJson    = Join-Path $RepoDir 'settings.json'
$TargetJson = Join-Path $ClaudeDir 'settings.json'

$item = Get-Item $TargetJson -ErrorAction SilentlyContinue
if ($item -and $item.LinkType -eq 'SymbolicLink' -and $item.Target -eq $SrcJson) {
    Log "$TargetJson already links to $SrcJson"
    $AgentsMode = if ($AgentCopied) { 'copy' } else { 'symlink' }
    $HookMode = 'not needed'
    if ($AgentCopied) { $HookMode = Install-PostMergeHook }
    Write-InstallLog -SettingsMode 'symlink' -AgentsMode $AgentsMode -HookMode $HookMode
    exit 0
}

if ($item -and -not $item.LinkType) {
    if ((Get-FileHash $TargetJson).Hash -ne (Get-FileHash $SrcJson).Hash) {
        $bak = "$TargetJson.bak.$(Get-Date -Format yyyyMMddHHmmss)"
        Copy-Item $TargetJson $bak
        Log "existing $TargetJson backed up to $bak; merge any keys you want (permissions, etc.) into $SrcJson"
    }
    Remove-Item $TargetJson
} elseif ($item) {
    Remove-Item $TargetJson
}

try {
    New-Item -ItemType SymbolicLink -Path $TargetJson -Target $SrcJson -ErrorAction Stop | Out-Null
    Log "linked $TargetJson -> $SrcJson (git pull in the clone is now the whole update)"
    $AgentsMode = if ($AgentCopied) { 'copy' } else { 'symlink' }
    Write-InstallLog -SettingsMode 'symlink' -AgentsMode $AgentsMode -HookMode 'not needed'
} catch {
    Copy-Item $SrcJson $TargetJson
    Log "symlink not permitted (enable Windows Developer Mode, or run as admin); copied instead."
    $HookMode = Install-PostMergeHook
    $AgentsMode = if ($AgentCopied) { 'copy' } else { 'symlink' }
    Write-InstallLog -SettingsMode 'copy' -AgentsMode $AgentsMode -HookMode $HookMode
}
