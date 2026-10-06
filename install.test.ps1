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

# Every subprocess install below writes its PATH change to this throwaway key, never to the real
# HKCU:\Environment. install.ps1 reads the key path from CLAUDE_SETTINGS_USER_ENV_KEY. The key
# and the variable are removed at the end of the file.
$TestEnvSub = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
$env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$TestEnvSub"
[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($TestEnvSub).Close()

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

# ---- copy-mode case: settings.json repeat run, no symlink rights (D: copy-mode-overwrites-no-backup) --
# Same shape as copymode1, but for the settings.json branch at the tail of install.ps1, not the
# skills branch. Skipped for the same honest reason when this runner holds symlink rights.
if ($SymlinkCapable) {
    Write-Host "SKIP: settingsrepeat1 (this runner holds symlink rights; the copy path cannot be exercised honestly without forcing it, see install.ps1 settings.json branch)"
} else {
    $Tmp3 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-settingsrepeat-" + [guid]::NewGuid().ToString('N'))
    $Co3  = Join-Path $Tmp3 'clone'
    $Cfg3 = Join-Path $Tmp3 'claude'
    New-Item -ItemType Directory -Force -Path $Co3, $Cfg3 | Out-Null
    try {
        Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Co3 'install.ps1')
        Set-Content -Path (Join-Path $Co3 'CLAUDE.md') -Value "# settingsrepeat1 content" -Encoding utf8
        Set-Content -Path (Join-Path $Co3 'settings.json') -Value '{"v":1}' -Encoding utf8
        Set-Content -Path (Join-Path $Co3 'landed-dirs.txt') -Value "skills" -Encoding utf8

        $env:CLAUDE_CONFIG_DIR = $Cfg3
        powershell -NoProfile -File (Join-Path $Co3 'install.ps1') *> $null
        if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: settingsrepeat1 run 1 exited $LASTEXITCODE"; $Failed++ }

        # Change the source settings.json between runs, the way a real `git pull` would.
        Set-Content -Path (Join-Path $Co3 'settings.json') -Value '{"v":2}' -Encoding utf8

        powershell -NoProfile -File (Join-Path $Co3 'install.ps1') *> $null
        if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: settingsrepeat1 run 2 exited $LASTEXITCODE"; $Failed++ }

        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        $Baks     = Get-ChildItem -Path $Cfg3 -Filter 'settings.json.bak.*' -ErrorAction SilentlyContinue
        $GotFile  = Join-Path $Cfg3 'settings.json'
        $GotValue = if (Test-Path $GotFile) { Get-Content -Raw $GotFile } else { $null }

        Check "settingsrepeat1: run 2 leaves no settings.json.bak.* under the config dir" (-not $Baks)
        Check "settingsrepeat1: settings.json lands after run 2" (Test-Path $GotFile)
        if ($GotValue) { Check "settingsrepeat1: settings.json holds run 2's content" (($GotValue | ConvertFrom-Json).v -eq 2) }
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $Tmp3 -ErrorAction SilentlyContinue
    }
}

# ---- copy-mode case: true first install backs up a person's own files once, no symlink rights --
# (D: copy-mode-overwrites-no-backup). Before any run (no .claude-settings-installed marker),
# plants a person's own skills/<shipped-name>/SKILL.md and agents/<shipped-name>.md under the
# fake config dir, under names install.ps1 itself ships, then runs install.ps1 twice.
if ($SymlinkCapable) {
    Write-Host "SKIP: firstinstall1 (this runner holds symlink rights; the copy path cannot be exercised honestly without forcing it, see install.ps1 skills/agents branches)"
} else {
    $Tmp4 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-firstinstall-" + [guid]::NewGuid().ToString('N'))
    $Co4  = Join-Path $Tmp4 'clone'
    $Cfg4 = Join-Path $Tmp4 'claude'
    New-Item -ItemType Directory -Force -Path $Co4, $Cfg4 | Out-Null
    try {
        Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Co4 'install.ps1')
        Set-Content -Path (Join-Path $Co4 'CLAUDE.md') -Value "# firstinstall1 content" -Encoding utf8
        Set-Content -Path (Join-Path $Co4 'settings.json') -Value '{}' -Encoding utf8
        Set-Content -Path (Join-Path $Co4 'landed-dirs.txt') -Value "skills`nagents" -Encoding utf8
        $SkillDir4 = Join-Path $Co4 'skills\sample-skill'
        New-Item -ItemType Directory -Force -Path $SkillDir4 | Out-Null
        Set-Content -Path (Join-Path $SkillDir4 'SKILL.md') -Value 'shipped skill v1' -Encoding utf8
        $AgentDirSrc = Join-Path $Co4 'agents'
        New-Item -ItemType Directory -Force -Path $AgentDirSrc | Out-Null
        Set-Content -Path (Join-Path $AgentDirSrc 'sample-agent.md') -Value 'shipped agent v1' -Encoding utf8

        # Plant the person's own pre-existing files before any run, no marker present yet.
        $CfgSkillDir = Join-Path $Cfg4 'skills\sample-skill'
        $CfgAgentDir = Join-Path $Cfg4 'agents'
        New-Item -ItemType Directory -Force -Path $CfgSkillDir, $CfgAgentDir | Out-Null
        Set-Content -Path (Join-Path $CfgSkillDir 'SKILL.md') -Value "person's own skill" -Encoding utf8
        Set-Content -Path (Join-Path $CfgAgentDir 'sample-agent.md') -Value "person's own agent" -Encoding utf8

        $env:CLAUDE_CONFIG_DIR = $Cfg4
        powershell -NoProfile -File (Join-Path $Co4 'install.ps1') *> $null
        if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: firstinstall1 run 1 exited $LASTEXITCODE"; $Failed++ }

        $SkillBaks1 = @(Get-ChildItem -Path (Join-Path $Cfg4 'skills') -Filter 'sample-skill.bak.*' -ErrorAction SilentlyContinue)
        $AgentBaks1 = @(Get-ChildItem -Path $CfgAgentDir -Filter 'sample-agent.md.bak.*' -ErrorAction SilentlyContinue)

        Check "firstinstall1: exactly one skill backup after run 1" ($SkillBaks1.Count -eq 1)
        Check "firstinstall1: exactly one agent backup after run 1" ($AgentBaks1.Count -eq 1)
        if ($SkillBaks1.Count -eq 1) {
            Check "firstinstall1: skill backup holds the person's content" ((Get-Content -Raw (Join-Path $SkillBaks1[0].FullName 'SKILL.md')).Trim() -eq "person's own skill")
        }
        if ($AgentBaks1.Count -eq 1) {
            Check "firstinstall1: agent backup holds the person's content" ((Get-Content -Raw $AgentBaks1[0].FullName).Trim() -eq "person's own agent")
        }
        $GotSkill = Join-Path $CfgSkillDir 'SKILL.md'
        $GotAgent = Join-Path $CfgAgentDir 'sample-agent.md'
        Check "firstinstall1: shipped skill content lands after run 1" ((Test-Path $GotSkill) -and (Get-Content -Raw $GotSkill).Trim() -eq 'shipped skill v1')
        Check "firstinstall1: shipped agent content lands after run 1" ((Test-Path $GotAgent) -and (Get-Content -Raw $GotAgent).Trim() -eq 'shipped agent v1')

        powershell -NoProfile -File (Join-Path $Co4 'install.ps1') *> $null
        if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: firstinstall1 run 2 exited $LASTEXITCODE"; $Failed++ }
        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue

        $SkillBaks2 = @(Get-ChildItem -Path (Join-Path $Cfg4 'skills') -Filter 'sample-skill.bak.*' -ErrorAction SilentlyContinue)
        $AgentBaks2 = @(Get-ChildItem -Path $CfgAgentDir -Filter 'sample-agent.md.bak.*' -ErrorAction SilentlyContinue)
        Check "firstinstall1: run 2 makes no new skill backup" ($SkillBaks2.Count -eq 1)
        Check "firstinstall1: run 2 makes no new agent backup" ($AgentBaks2.Count -eq 1)
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $Tmp4 -ErrorAction SilentlyContinue
    }
}

# ---- envkey1: a subprocess install writes the absolute bin to the key named by the env var -----
# Reads the throwaway key, never HKCU:\Environment. Red while the installer ignores the variable.
$Tmp5 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-envkey-" + [guid]::NewGuid().ToString('N'))
$Co5  = Join-Path $Tmp5 'clone'
$Cfg5 = Join-Path $Tmp5 'claude'
New-Item -ItemType Directory -Force -Path $Co5, $Cfg5 | Out-Null
try {
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Co5 'install.ps1')
    Set-Content -Path (Join-Path $Co5 'CLAUDE.md') -Value "# envkey1 content" -Encoding utf8
    Set-Content -Path (Join-Path $Co5 'settings.json') -Value '{}' -Encoding utf8
    Set-Content -Path (Join-Path $Co5 'landed-dirs.txt') -Value "skills" -Encoding utf8
    $k5 = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($TestEnvSub)
    $pre5 = ($env:CLAUDE_SETTINGS_USER_ENV_KEY -eq "HKCU:\$TestEnvSub") -and ($null -ne $k5) -and ($null -eq $k5.GetValue('Path'))
    if ($k5) { $k5.Close() }
    if (-not $pre5) { Write-Host "FAIL: envkey1 fixture: var unset, key missing, or Path already set"; $Failed++ }
    $env:CLAUDE_CONFIG_DIR = $Cfg5
    powershell -NoProfile -File (Join-Path $Co5 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: envkey1 install exited $LASTEXITCODE"; $Failed++ }
    Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
    $k5 = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($TestEnvSub)
    $got5 = if ($k5) { $k5.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) } else { '' }
    if ($k5) { $k5.Close() }
    Check "envkey1: subprocess install writes the absolute bin path to the key in CLAUDE_SETTINGS_USER_ENV_KEY" (($got5 -split ';') -contains (Join-Path $env:USERPROFILE '.claude\bin'))
} finally {
    Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Tmp5 -ErrorAction SilentlyContinue
}

# ---- Join-BinPath: pure PATH-string function; never reads or writes the real user PATH ------
# Loaded on its own so a missing function fails these cases, not the whole file.
$jb = $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Join-BinPath' }, $false) | Select-Object -First 1
if (-not $jb) {
    Check "joinbin: install.ps1 defines function Join-BinPath" $false
} else {
    Invoke-Expression $jb.Extent.Text
    $Bin = 'C:\Users\x\.claude\bin'
    Check "joinbin: absent bin is appended with ';'" ((Join-BinPath 'C:\a;C:\b' $Bin) -eq "C:\a;C:\b;$Bin")
    Check "joinbin: present bin returns Current unchanged" ((Join-BinPath "C:\a;$Bin;C:\b" $Bin) -eq "C:\a;$Bin;C:\b")
    Check "joinbin: match ignores case" ((Join-BinPath 'C:\a;c:\users\X\.CLAUDE\bin' $Bin) -eq 'C:\a;c:\users\X\.CLAUDE\bin')
    Check "joinbin: match ignores a trailing backslash" ((Join-BinPath "C:\a;$Bin\" $Bin) -eq "C:\a;$Bin\")
    Check "joinbin: empty Current returns Bin alone" ((Join-BinPath '' $Bin) -eq $Bin)
    Check "joinbin: a longer sibling dir is not a match" ((Join-BinPath "C:\a;$Bin-old" $Bin) -eq "C:\a;$Bin-old;$Bin")
}
Check "joinbin: install.ps1 calls Set-UserBinPath on HKCU:\Environment" ($Source -match "Set-UserBinPath\s+(-KeyPath\s+)?['""]?HKCU:\\Environment")

# Join-BinPath edge cases (contract 2)
if ($jb) {
    $Abs = Join-Path $env:USERPROFILE '.claude\bin'
    Check "joinbin: Current ending in ';' gives no ';;'" ((Join-BinPath 'C:\a;' $Abs) -eq "C:\a;$Abs")
    Check "joinbin: a %USERPROFILE% entry counts as the absolute bin" ((Join-BinPath 'C:\a;%USERPROFILE%\.claude\bin' $Abs) -eq 'C:\a;%USERPROFILE%\.claude\bin')
}

# ---- Set-UserBinPath: registry round trip against a THROWAWAY key, never the real HKCU:\Environment
$sb = $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Set-UserBinPath' }, $false) | Select-Object -First 1
if (-not $sb) {
    Check "setbin: install.ps1 defines function Set-UserBinPath" $false
} else {
    Invoke-Expression $sb.Extent.Text
    $Sub = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
    $Reg = [Microsoft.Win32.Registry]::CurrentUser
    $Abs = Join-Path $env:USERPROFILE '.claude\bin'
    $Raw = [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames
    try {
        $k = $Reg.CreateSubKey($Sub)
        $k.SetValue('Path', '%TEMP%\x;C:\a', [Microsoft.Win32.RegistryValueKind]::ExpandString)
        $k.Close()
        $pre = $Reg.OpenSubKey($Sub)
        $preOk = ($pre.GetValueKind('Path') -eq 'ExpandString') -and ($pre.GetValue('Path', '', $Raw) -eq '%TEMP%\x;C:\a')
        $pre.Close()
        if (-not $preOk) { Write-Host "FAIL: setbin fixture did not build an ExpandString value"; $Failed++ }
        Set-UserBinPath "HKCU:\$Sub" $Abs
        $k = $Reg.OpenSubKey($Sub)
        Check "setbin: ExpandString kind is kept" ($k.GetValueKind('Path') -eq 'ExpandString')
        Check "setbin: existing %TEMP%\x entry stays literal and the absolute bin is appended" ($k.GetValue('Path', '', $Raw) -eq "%TEMP%\x;C:\a;$Abs")
        $k.Close()
        Set-UserBinPath "HKCU:\$Sub" $Abs
        $k = $Reg.OpenSubKey($Sub)
        Check "setbin: a second call changes nothing" ($k.GetValue('Path', '', $Raw) -eq "%TEMP%\x;C:\a;$Abs")
        $k.Close()
        $k = $Reg.OpenSubKey($Sub, $true); $k.DeleteValue('Path'); $k.Close()
        Set-UserBinPath "HKCU:\$Sub" $Abs
        $k = $Reg.OpenSubKey($Sub)
        Check "setbin: a missing Path value is created as ExpandString holding the bin" (($k.GetValueKind('Path') -eq 'ExpandString') -and ($k.GetValue('Path', '', $Raw) -eq $Abs))
        $k.Close()
    } finally {
        try { $Reg.DeleteSubKeyTree($Sub, $false) } catch { }
    }
}

# ---- gap: the embedded post-merge hook body (install.ps1's Install-PostMergeHook) is not --
# covered here. It is a heredoc written into .git\hooks\post-merge and run by `git` itself on
# a real `git pull`, under `sh` inside Git Bash, not by any PowerShell function this file can
# load or call directly. Exercising it for real needs a real git repo, a real merge that
# changes install.ps1 or a skill, and a real Git-Bash `sh` to run the written hook body, none
# of which this harness drives. Reported as a gap, not faked.

try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($TestEnvSub, $false) } catch { }
Remove-Item Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
