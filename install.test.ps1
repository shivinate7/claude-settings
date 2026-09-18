# Tests for the CLAUDE.md pointer block of install.ps1. Runs on PowerShell 5.1 and 7.
#
#   pwsh -NoProfile -File .\install.test.ps1
#
# Loads only the Write-Pointer function (and its Log helper) from install.ps1, so the rest of
# the installer never touches this machine. Prints one line per case; exits 1 on any failure.
$ErrorActionPreference = 'Stop'

$Here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Get-Content -Raw (Join-Path $Here 'install.ps1')
$Ast    = [System.Management.Automation.Language.Parser]::ParseInput($Source, [ref]$null, [ref]$null)
foreach ($name in @('Log', 'Write-Pointer')) {
    $fn = $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $false) | Select-Object -First 1
    if (-not $fn) { Write-Host "FAIL: install.ps1 has no function $name"; exit 1 }
    Invoke-Expression $fn.Extent.Text
}
function Log([string]$msg) { }   # quiet during the tests

$Failed = 0
function Check([string]$name, [bool]$ok) {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: $name"; $script:Failed++ }
}

$Tmp = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-test-" + [guid]::NewGuid().ToString('N'))
$RepoDir   = Join-Path $Tmp 'clone'
$ClaudeDir = Join-Path $Tmp 'claude'
New-Item -ItemType Directory -Force -Path $RepoDir, $ClaudeDir | Out-Null
$TargetMd = Join-Path $ClaudeDir 'CLAUDE.md'
$Pointer  = '@' + (($RepoDir -replace '\\', '/').TrimEnd('/')) + '/CLAUDE.md'

try {
    # (a) fresh write: first byte is '@', no BOM
    Write-Pointer -RepoDir $RepoDir -ClaudeDir $ClaudeDir
    $bytes = [IO.File]::ReadAllBytes($TargetMd)
    Check "fresh write starts with 0x40 '@' (no BOM)" ($bytes.Length -gt 0 -and $bytes[0] -eq 0x40)
    Check "fresh write holds the pointer text" ([IO.File]::ReadAllText($TargetMd) -eq $Pointer)

    # (b) rerun over an identical pointer: no backup
    Write-Pointer -RepoDir $RepoDir -ClaudeDir $ClaudeDir
    Check "rerun over identical pointer makes no .bak" (-not (Get-ChildItem $ClaudeDir -Filter 'CLAUDE.md.bak.*'))

    # (c) rerun over a BOM-prefixed pointer (written by the old installer): no backup, BOM removed
    [IO.File]::WriteAllText($TargetMd, $Pointer, [Text.UTF8Encoding]::new($true))
    if ([IO.File]::ReadAllBytes($TargetMd)[0] -ne 0xEF) { Write-Host "FAIL: fixture did not get a BOM"; exit 1 }
    Write-Pointer -RepoDir $RepoDir -ClaudeDir $ClaudeDir
    Check "rerun over BOM-prefixed pointer makes no .bak" (-not (Get-ChildItem $ClaudeDir -Filter 'CLAUDE.md.bak.*'))
    Check "rerun over BOM-prefixed pointer rewrites without BOM" ([IO.File]::ReadAllBytes($TargetMd)[0] -eq 0x40)

    # (d) a different existing file is still backed up
    [IO.File]::WriteAllText($TargetMd, "# my own notes`n", [Text.UTF8Encoding]::new($false))
    Write-Pointer -RepoDir $RepoDir -ClaudeDir $ClaudeDir
    Check "different existing CLAUDE.md is backed up" ([bool](Get-ChildItem $ClaudeDir -Filter 'CLAUDE.md.bak.*'))
} finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
