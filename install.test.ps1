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


# ---- copy-mode case: skills/ under a real install.ps1 run, twice, no symlink rights -----------
# Mirrors hooks/test_install_src.sh's copymode_case1 (D: copy-mode-overwrites-no-backup). Runs
# the WHOLE install.ps1 as a subprocess (not just one extracted function) against a fake
# checkout and a fake CLAUDE_CONFIG_DIR, twice, so the loop at install.ps1's skills branch
# (lines 169-197) takes the real New-Item -ItemType SymbolicLink -> catch -> Copy-Item path
# this machine actually hits. A machine WITH symlink rights would take the symlink branch
# instead and pass by not exercising the bug at all, so that case is skipped there with a
# reason instead of a false pass.
$SymlinkCapable = $true
$ProbeLink = Join-Path ([IO.Path]::GetTempPath()) ("symprobe-" + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType SymbolicLink -Path $ProbeLink -Target $Here -ErrorAction Stop | Out-Null
    Remove-Item $ProbeLink -Force -ErrorAction SilentlyContinue
} catch {
    $SymlinkCapable = $false
}

if ($SymlinkCapable) {
    Write-Host "SKIP: copymode1 (this runner holds symlink rights; the copy path cannot be exercised honestly without forcing it, see install.ps1 skills branch)"
} else {
    $Tmp2    = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-copymode-" + [guid]::NewGuid().ToString('N'))
    $Co      = Join-Path $Tmp2 'clone'
    $Cfg     = Join-Path $Tmp2 'claude'
    New-Item -ItemType Directory -Force -Path $Co, $Cfg | Out-Null
    try {
        Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Co 'install.ps1')
        Set-Content -Path (Join-Path $Co 'CLAUDE.md') -Value "# copymode1 content" -Encoding utf8
        Set-Content -Path (Join-Path $Co 'settings.json') -Value '{}' -Encoding utf8
        Set-Content -Path (Join-Path $Co 'landed-dirs.txt') -Value "skills" -Encoding utf8
        $SkillDir = Join-Path $Co 'skills\sample-skill'
        New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
        Set-Content -Path (Join-Path $SkillDir 'SKILL.md') -Value 'v1' -Encoding utf8

        $env:CLAUDE_CONFIG_DIR = $Cfg
        powershell -NoProfile -File (Join-Path $Co 'install.ps1') *> $null
        if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: copymode1 run 1 exited $LASTEXITCODE"; $Failed++ }

        # Change the skill's source content between runs, the way a real `git pull` would.
        Set-Content -Path (Join-Path $SkillDir 'SKILL.md') -Value 'v2' -Encoding utf8

        powershell -NoProfile -File (Join-Path $Co 'install.ps1') *> $null
        if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: copymode1 run 2 exited $LASTEXITCODE"; $Failed++ }

        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        $Baks     = Get-ChildItem -Path $Cfg -Recurse -Filter '*.bak.*' -ErrorAction SilentlyContinue
        $GotFile  = Join-Path $Cfg 'skills\sample-skill\SKILL.md'
        $GotValue = if (Test-Path $GotFile) { Get-Content -Raw $GotFile } else { $null }

        Check "copymode1: run 2 leaves no .bak under the config dir" (-not $Baks)
        Check "copymode1: sample-skill/SKILL.md lands after run 2" (Test-Path $GotFile)
        if ($GotValue) { Check "copymode1: sample-skill/SKILL.md holds run 2's content (v2)" ($GotValue.Trim() -eq 'v2') }
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $Tmp2 -ErrorAction SilentlyContinue
    }
}

# ---- gap: the embedded post-merge hook body (install.ps1's Install-PostMergeHook) is not --
# covered here. It is a heredoc written into .git\hooks\post-merge and run by `git` itself on
# a real `git pull`, under `sh` inside Git Bash, not by any PowerShell function this file can
# load or call directly. Exercising it for real needs a real git repo, a real merge that
# changes install.ps1 or a skill, and a real Git-Bash `sh` to run the written hook body, none
# of which this harness drives. Reported as a gap, not faked.

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
