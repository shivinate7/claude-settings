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


# ---- copy-mode cases: CLAUDE_SETTINGS_FORCE_COPY=1 forces copy mode on any runner -------------
# install.ps1's New-Link throws while that variable is 1, so every skills, agents and settings
# link try falls back to Copy-Item, on a machine with symlink rights or without. Each case first
# checks that the landed names are copies, not links. A seam that never reaches the child process
# then fails the case, instead of passing it without exercising the copy path.
# (D: copy-mode-overwrites-no-backup)
# install.ps1 is the Windows installer (kernel32 MoveFileEx). The cases below that run it run only
# on Windows. Elsewhere each prints SKIP and the file goes on. nonwin1 is the exception: it runs
# install.ps1 off Windows and expects exit 0 there.

# True when $Path is a symlink or junction (a reparse point). A missing path is not a link.
function Test-ReparsePoint([string]$Path) {
    $i = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $i) { return $false }
    return (([int]$i.Attributes) -band [int][IO.FileAttributes]::ReparsePoint) -ne 0
}

# Copies install.ps1 into a fixture clone at $Dest, and install.py too when the repo has one.
# Every fixture clone below is built through this, so none loses the installer spine (L1).
function Copy-Installer([string]$Dest) {
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Dest 'install.ps1')
    $py = Join-Path $Here 'install.py'
    if (Test-Path $py) { Copy-Item $py (Join-Path $Dest 'install.py') }
}

# Every subprocess install below writes its PATH change to this throwaway key, never to the real
# HKCU:\Environment. install.ps1 reads the key path from CLAUDE_SETTINGS_USER_ENV_KEY. The key
# and the variable are removed at the end of the file.
# No registry off Windows: there the registry cases SKIP and install.ps1 skips the PATH write.
# Windows PowerShell 5.1 (Desktop) or pwsh on Windows. Off Windows, $IsWindows is $false.
$IsWin  = ($PSVersionTable.PSEdition -eq 'Desktop') -or [bool]$IsWindows
$PsHost = (Get-Process -Id $PID).Path   # child installs run under this host; no literal `powershell`
if (-not $env:USERPROFILE) { $env:USERPROFILE = $HOME }   # the pure Join-BinPath cases expand %USERPROFILE%
$TestEnvSub = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
if ($IsWin) {
    $env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$TestEnvSub"
    [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($TestEnvSub).Close()
}
try {

if ($IsWin) {
# ---- copy-mode case: skills/ under a real install.ps1 run, twice ------------------------------
# Mirrors hooks/test_install_src.sh's copymode_case1 (D: copy-mode-overwrites-no-backup). Runs
# the WHOLE install.ps1 as a subprocess (not just one extracted function) against a fake
# checkout and a fake CLAUDE_CONFIG_DIR, twice, so the skills branch takes the copy path
# (New-Link throws, Install-Dir copies).
$Tmp2 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-copymode-" + [guid]::NewGuid().ToString('N'))
$Co   = Join-Path $Tmp2 'clone'
$Cfg  = Join-Path $Tmp2 'claude'
New-Item -ItemType Directory -Force -Path $Co, $Cfg | Out-Null
try {
    Copy-Installer $Co
    Set-Content -Path (Join-Path $Co 'CLAUDE.md') -Value "# copymode1 content" -Encoding utf8
    Set-Content -Path (Join-Path $Co 'settings.json') -Value '{}' -Encoding utf8
    Set-Content -Path (Join-Path $Co 'landed-dirs.txt') -Value "skills" -Encoding utf8
    $SkillDir = Join-Path $Co 'skills\sample-skill'
    New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
    Set-Content -Path (Join-Path $SkillDir 'SKILL.md') -Value 'v1' -Encoding utf8

    $env:CLAUDE_CONFIG_DIR = $Cfg
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    & $PsHost -NoProfile -File (Join-Path $Co 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: copymode1 run 1 exited $LASTEXITCODE"; $Failed++ }
    Check "copymode1: sample-skill is a copy, not a link, after run 1" (-not (Test-ReparsePoint (Join-Path $Cfg 'skills\sample-skill')))

    # Change the skill's source content between runs, the way a real `git pull` would.
    Set-Content -Path (Join-Path $SkillDir 'SKILL.md') -Value 'v2' -Encoding utf8

    & $PsHost -NoProfile -File (Join-Path $Co 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: copymode1 run 2 exited $LASTEXITCODE"; $Failed++ }

    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    $Baks     = Get-ChildItem -Path $Cfg -Recurse -Filter '*.bak.*' -ErrorAction SilentlyContinue
    $GotFile  = Join-Path $Cfg 'skills\sample-skill\SKILL.md'
    $GotValue = if (Test-Path $GotFile) { Get-Content -Raw $GotFile } else { $null }

    Check "copymode1: run 2 leaves no .bak under the config dir" (-not $Baks)
    Check "copymode1: sample-skill/SKILL.md lands after run 2" (Test-Path $GotFile)
    if ($GotValue) { Check "copymode1: sample-skill/SKILL.md holds run 2's content (v2)" ($GotValue.Trim() -eq 'v2') }
} finally {
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Tmp2 -ErrorAction SilentlyContinue
}

# ---- copy-mode case: settings.json repeat run (D: copy-mode-overwrites-no-backup) -------------
# Same shape as copymode1, for the settings.json branch at the tail of install.ps1, not the
# skills branch.
$Tmp3 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-settingsrepeat-" + [guid]::NewGuid().ToString('N'))
$Co3  = Join-Path $Tmp3 'clone'
$Cfg3 = Join-Path $Tmp3 'claude'
New-Item -ItemType Directory -Force -Path $Co3, $Cfg3 | Out-Null
try {
    Copy-Installer $Co3
    Set-Content -Path (Join-Path $Co3 'CLAUDE.md') -Value "# settingsrepeat1 content" -Encoding utf8
    Set-Content -Path (Join-Path $Co3 'settings.json') -Value '{"v":1}' -Encoding utf8
    Set-Content -Path (Join-Path $Co3 'landed-dirs.txt') -Value "skills" -Encoding utf8

    $env:CLAUDE_CONFIG_DIR = $Cfg3
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    & $PsHost -NoProfile -File (Join-Path $Co3 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: settingsrepeat1 run 1 exited $LASTEXITCODE"; $Failed++ }
    Check "settingsrepeat1: settings.json is a copy, not a link, after run 1" (-not (Test-ReparsePoint (Join-Path $Cfg3 'settings.json')))

    # Change the source settings.json between runs, the way a real `git pull` would.
    Set-Content -Path (Join-Path $Co3 'settings.json') -Value '{"v":2}' -Encoding utf8

    & $PsHost -NoProfile -File (Join-Path $Co3 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: settingsrepeat1 run 2 exited $LASTEXITCODE"; $Failed++ }

    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    $Baks     = Get-ChildItem -Path $Cfg3 -Filter 'settings.json.bak.*' -ErrorAction SilentlyContinue
    $GotFile  = Join-Path $Cfg3 'settings.json'
    $GotValue = if (Test-Path $GotFile) { Get-Content -Raw $GotFile } else { $null }

    Check "settingsrepeat1: run 2 leaves no settings.json.bak.* under the config dir" (-not $Baks)
    Check "settingsrepeat1: settings.json lands after run 2" (Test-Path $GotFile)
    if ($GotValue) { Check "settingsrepeat1: settings.json holds run 2's content" (($GotValue | ConvertFrom-Json).v -eq 2) }
} finally {
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Tmp3 -ErrorAction SilentlyContinue
}

# ---- copy-mode case: true first install backs up a person's own files once --------------------
# (D: copy-mode-overwrites-no-backup). Before any run (no .claude-settings-installed marker),
# plants a person's own skills/<shipped-name>/SKILL.md and agents/<shipped-name>.md under the
# fake config dir, under names install.ps1 itself ships, then runs install.ps1 twice.
$Tmp4 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-firstinstall-" + [guid]::NewGuid().ToString('N'))
$Co4  = Join-Path $Tmp4 'clone'
$Cfg4 = Join-Path $Tmp4 'claude'
New-Item -ItemType Directory -Force -Path $Co4, $Cfg4 | Out-Null
try {
    Copy-Installer $Co4
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
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    & $PsHost -NoProfile -File (Join-Path $Co4 'install.ps1') *> $null
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
    Check "firstinstall1: shipped skill is a copy, not a link, after run 1" (-not (Test-ReparsePoint $CfgSkillDir))
    Check "firstinstall1: shipped agent is a copy, not a link, after run 1" (-not (Test-ReparsePoint $GotAgent))

    & $PsHost -NoProfile -File (Join-Path $Co4 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: firstinstall1 run 2 exited $LASTEXITCODE"; $Failed++ }
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue

    $SkillBaks2 = @(Get-ChildItem -Path (Join-Path $Cfg4 'skills') -Filter 'sample-skill.bak.*' -ErrorAction SilentlyContinue)
    $AgentBaks2 = @(Get-ChildItem -Path $CfgAgentDir -Filter 'sample-agent.md.bak.*' -ErrorAction SilentlyContinue)
    Check "firstinstall1: run 2 makes no new skill backup" ($SkillBaks2.Count -eq 1)
    Check "firstinstall1: run 2 makes no new agent backup" ($AgentBaks2.Count -eq 1)
} finally {
    Remove-Item Env:\CLAUDE_CONFIG_DIR, Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Tmp4 -ErrorAction SilentlyContinue
}

# ---- envkey1: a subprocess install writes the absolute bin to the key named by the env var -----
# Reads the throwaway key, never HKCU:\Environment. Red while the installer ignores the variable.
$Tmp5 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-envkey-" + [guid]::NewGuid().ToString('N'))
$Co5  = Join-Path $Tmp5 'clone'
$Cfg5 = Join-Path $Tmp5 'claude'
New-Item -ItemType Directory -Force -Path $Co5, $Cfg5 | Out-Null
try {
    Copy-Installer $Co5
    Set-Content -Path (Join-Path $Co5 'CLAUDE.md') -Value "# envkey1 content" -Encoding utf8
    Set-Content -Path (Join-Path $Co5 'settings.json') -Value '{}' -Encoding utf8
    Set-Content -Path (Join-Path $Co5 'landed-dirs.txt') -Value "skills" -Encoding utf8
    # Its own fresh key: the shared key already holds a Path from the earlier installs.
    $Sub5 = 'Software\claude-settings-test-' + [guid]::NewGuid().ToString('N')
    [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($Sub5).Close()
    $SharedKey = $env:CLAUDE_SETTINGS_USER_ENV_KEY
    $env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$Sub5"
    $k5 = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($Sub5)
    $pre5 = ($env:CLAUDE_SETTINGS_USER_ENV_KEY -eq "HKCU:\$Sub5") -and ($null -ne $k5) -and ($null -eq $k5.GetValue('Path'))
    if ($k5) { $k5.Close() }
    if (-not $pre5) { Write-Host "FAIL: envkey1 fixture: var unset, key missing, or Path already set"; $Failed++ }
    $env:CLAUDE_CONFIG_DIR = $Cfg5
    & $PsHost -NoProfile -File (Join-Path $Co5 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: envkey1 install exited $LASTEXITCODE"; $Failed++ }
    Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
    $k5 = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($Sub5)
    $got5 = if ($k5) { $k5.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) } else { '' }
    if ($k5) { $k5.Close() }
    Check "envkey1: subprocess install writes the absolute bin path to the key in CLAUDE_SETTINGS_USER_ENV_KEY" (($got5 -split ';') -contains (Join-Path $env:USERPROFILE '.claude\bin'))
} finally {
    Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
    if ($SharedKey) { $env:CLAUDE_SETTINGS_USER_ENV_KEY = $SharedKey }
    if ($Sub5) { try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($Sub5, $false) } catch { } }
    Remove-Item -Recurse -Force $Tmp5 -ErrorAction SilentlyContinue
}
    Write-Host "SKIP: nonwin1 (this is Windows)"
} else {
    Write-Host "SKIP: copymode1: install.ps1 runs only on Windows"
    Write-Host "SKIP: settingsrepeat1: install.ps1 runs only on Windows"
    Write-Host "SKIP: firstinstall1: install.ps1 runs only on Windows"
    Write-Host "SKIP: envkey1: install.ps1 runs only on Windows"
}

# ---- nonwin1: install.ps1 exits 0 off Windows (no registry). Runs off Windows only. ------------
# Off Windows install.ps1 must skip the PATH write and still exit 0 (it never reaches the registry).
# Red while install.ps1 fails off Windows (kernel32 MoveFileEx): that defect is the builder's.
if (-not $IsWin) {
    $Tmp5 = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-envkey-" + [guid]::NewGuid().ToString('N'))
    $Co5  = Join-Path $Tmp5 'clone'
    $Cfg5 = Join-Path $Tmp5 'claude'
    New-Item -ItemType Directory -Force -Path $Co5, $Cfg5 | Out-Null
    try {
        Copy-Installer $Co5
        Set-Content -Path (Join-Path $Co5 'CLAUDE.md') -Value "# nonwin1 content" -Encoding utf8
        Set-Content -Path (Join-Path $Co5 'settings.json') -Value '{}' -Encoding utf8
        Set-Content -Path (Join-Path $Co5 'landed-dirs.txt') -Value "skills" -Encoding utf8
        $env:CLAUDE_CONFIG_DIR = $Cfg5
        & $PsHost -NoProfile -File (Join-Path $Co5 'install.ps1') *> $null
        $rc5 = $LASTEXITCODE
        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        Check "nonwin1: subprocess install exits 0 off Windows (no registry)" ($rc5 -eq 0)
    } finally {
        Remove-Item Env:\CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $Tmp5 -ErrorAction SilentlyContinue
    }
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
# Contract: pure function Get-UserEnvKey returns $env:CLAUDE_SETTINGS_USER_ENV_KEY when set, else
# 'HKCU:\Environment'; the installer passes its result to Set-UserBinPath. Behaviour, not text.
$ge = $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-UserEnvKey' }, $false) | Select-Object -First 1
if (-not $ge) {
    Check "envkey: install.ps1 defines function Get-UserEnvKey" $false
} else {
    Invoke-Expression $ge.Extent.Text
    $savedKey = $env:CLAUDE_SETTINGS_USER_ENV_KEY
    try {
        Remove-Item Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue
        $pre = $null -eq $env:CLAUDE_SETTINGS_USER_ENV_KEY
        Check "envkey: with the var unset, Get-UserEnvKey returns HKCU:\Environment" ($pre -and (Get-UserEnvKey) -eq 'HKCU:\Environment')
        $env:CLAUDE_SETTINGS_USER_ENV_KEY = 'HKCU:\Software\claude-settings-test-x'
        Check "envkey: with the var set, Get-UserEnvKey returns it" ((Get-UserEnvKey) -eq 'HKCU:\Software\claude-settings-test-x')
    } finally {
        if ($savedKey) { $env:CLAUDE_SETTINGS_USER_ENV_KEY = $savedKey } else { Remove-Item Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue }
    }
}

# Join-BinPath edge cases. Contract: Join-BinPath Current Bin Kind; a %VAR% entry counts as
# present only when Kind is ExpandString. Under String (REG_SZ) it is a dead literal entry.
if ($jb) {
    # Concatenate with '\', not Join-Path: Join-Path joins with '/' on Linux, while the expanded
    # %USERPROFILE%\.claude\bin entry always has '\', so the two would never match there.
    $Abs = "$env:USERPROFILE\.claude\bin"
    $KExp = [Microsoft.Win32.RegistryValueKind]::ExpandString
    $KStr = [Microsoft.Win32.RegistryValueKind]::String
    Check "joinbin: Current ending in ';' gives no ';;'" ((Join-BinPath 'C:\a;' $Abs $KExp) -eq "C:\a;$Abs")
    Check "joinbin: ExpandString: a %USERPROFILE% entry counts as the absolute bin" ((Join-BinPath 'C:\a;%USERPROFILE%\.claude\bin' $Abs $KExp) -eq 'C:\a;%USERPROFILE%\.claude\bin')
    Check "joinbin: String: a %USERPROFILE% entry is dead, absolute bin appended, dead entry kept" ((Join-BinPath 'C:\a;%USERPROFILE%\.claude\bin' $Abs $KStr) -eq "C:\a;%USERPROFILE%\.claude\bin;$Abs")
}

# ---- Set-UserBinPath: registry round trip against a THROWAWAY key, never the real HKCU:\Environment
$sb = $Ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Set-UserBinPath' }, $false) | Select-Object -First 1
if (-not $IsWin) {
    Write-Host "SKIP: setbin (no registry off Windows)"
} elseif (-not $sb) {
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
        $null = Set-UserBinPath "HKCU:\$Sub" $Abs
        $k = $Reg.OpenSubKey($Sub)
        Check "setbin: ExpandString kind is kept" ($k.GetValueKind('Path') -eq 'ExpandString')
        Check "setbin: existing %TEMP%\x entry stays literal and the absolute bin is appended" ($k.GetValue('Path', '', $Raw) -eq "%TEMP%\x;C:\a;$Abs")
        $k.Close()
        $null = Set-UserBinPath "HKCU:\$Sub" $Abs
        $k = $Reg.OpenSubKey($Sub)
        Check "setbin: a second call changes nothing" ($k.GetValue('Path', '', $Raw) -eq "%TEMP%\x;C:\a;$Abs")
        $k.Close()
        $k = $Reg.OpenSubKey($Sub, $true); $k.DeleteValue('Path'); $k.Close()
        $null = Set-UserBinPath "HKCU:\$Sub" $Abs
        $k = $Reg.OpenSubKey($Sub)
        Check "setbin: a missing Path value is created as ExpandString holding the bin" (($k.GetValueKind('Path') -eq 'ExpandString') -and ($k.GetValue('Path', '', $Raw) -eq $Abs))
        $k.Close()
        # REG_SZ holding a literal %USERPROFILE% entry: it is dead, so the absolute bin is appended
        $k = $Reg.OpenSubKey($Sub, $true)
        $k.SetValue('Path', '%USERPROFILE%\.claude\bin', [Microsoft.Win32.RegistryValueKind]::String)
        $k.Close()
        $pre = $Reg.OpenSubKey($Sub)
        $preOk = ($pre.GetValueKind('Path') -eq 'String') -and ($pre.GetValue('Path', '', $Raw) -eq '%USERPROFILE%\.claude\bin')
        $pre.Close()
        if (-not $preOk) { Write-Host "FAIL: setbin fixture did not build a String value"; $Failed++ }
        $null = Set-UserBinPath "HKCU:\$Sub" $Abs
        $k = $Reg.OpenSubKey($Sub)
        Check "setbin: REG_SZ with a literal %USERPROFILE% entry stays String and gets the absolute bin appended" (($k.GetValueKind('Path') -eq 'String') -and ($k.GetValue('Path', '', $Raw) -eq "%USERPROFILE%\.claude\bin;$Abs"))
        $k.Close()
    } finally {
        try { $Reg.DeleteSubKeyTree($Sub, $false) } catch { }
    }
}

# ---- P1, P3, P4, P6: installer parity (Windows). Each case is red on today's install.ps1. ----------
# Each builds its own fixture under a temp root. CLAUDE_CONFIG_DIR and HOME must sit under that root,
# so the real ~\.claude and the real HKCU:\Environment are never written: Assert-Scratch throws before
# a child run that would break that rule. Child runs use Start-Process, so their output goes to a log.
function Assert-Scratch([string]$Path, [string]$Root) {
    if (-not $Path.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)) { throw "refusing: $Path is outside $Root" }
}

# Runs $Exe as a child in $WorkDir, output to $Log. Returns the exit code.
function Invoke-Child([string]$Exe, [string[]]$ArgList, [string]$WorkDir, [string]$Log) {
    $p = Start-Process -FilePath $Exe -ArgumentList $ArgList -WorkingDirectory $WorkDir -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $Log -RedirectStandardError ($Log + '.err')
    return $p.ExitCode
}

# Writes UTF-8 without a BOM, the text as given.
function Write-Plain([string]$Path, [string]$Text) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

# Restores one environment variable; an unset value removes it (an empty value would read as unset).
function Restore-Env([string]$Name, $Value) {
    if ($null -eq $Value) { Remove-Item "Env:\$Name" -ErrorAction SilentlyContinue } else { Set-Item "Env:\$Name" $Value }
}

# Git Bash's bash, from git's own install dir (never WSL's bash on PATH). Empty when absent.
function Get-GitBash {
    $b = Join-Path $env:ProgramFiles 'Git\bin\bash.exe'
    if (Test-Path -LiteralPath $b) { return $b }
    return ''
}

# Empty when this runner can make a symlink, else the reason it cannot.
function Get-LinkBlocker {
    $d = Join-Path ([IO.Path]::GetTempPath()) ('link-probe-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $d | Out-Null
    try {
        Write-Plain (Join-Path $d 'target') 'x'
        New-Item -ItemType SymbolicLink -Path (Join-Path $d 'link') -Target (Join-Path $d 'target') -ErrorAction Stop | Out-Null
        return ''
    } catch {
        return $_.Exception.Message
    } finally {
        Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $IsWin) {
    Write-Host 'SKIP: P1, P3, P4, P6 installer parity (Windows only)'
} else {

# ---- P1: ps1, then sh, then ps1 on one home makes no new CLAUDE.md.bak -------------------------
# The sh side writes "@~/..." when the clone sits under $HOME; the ps1 side writes "@C:/...". Today
# the pointer flips on each hand-over, so every flip backs CLAUDE.md up. One pointer form fixes it.
$GitBash = Get-GitBash
$P1 = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-p1-' + [guid]::NewGuid().ToString('N'))
try {
    if (-not $GitBash) {
        Write-Host 'SKIP: P1 pointer parity (Git Bash not found under Program Files)'
    } else {
        $P1Home  = Join-Path $P1 'home'
        $P1Clone = Join-Path $P1Home 'clone'
        $P1Cfg   = Join-Path $P1Home '.claude'
        New-Item -ItemType Directory -Force -Path $P1Clone, $P1Cfg | Out-Null
        Copy-Installer $P1Clone
        Copy-Item (Join-Path $Here 'install.sh') (Join-Path $P1Clone 'install.sh')
        Write-Plain (Join-Path $P1Clone 'CLAUDE.md') "# p1 content`n"
        Write-Plain (Join-Path $P1Clone 'settings.json') "{}`n"
        Write-Plain (Join-Path $P1Clone 'landed-dirs.txt') "skills`n"
        $ps1Args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $P1Clone 'install.ps1') + '"'))
        $savedCfg = $env:CLAUDE_CONFIG_DIR; $savedHome = $env:HOME
        try {
            Assert-Scratch $P1Cfg $P1; Assert-Scratch $P1Home $P1
            $env:CLAUDE_CONFIG_DIR = $P1Cfg; $env:HOME = $P1Home
            $rcA = Invoke-Child $PsHost $ps1Args $P1Clone (Join-Path $P1 'p1-a.log')
            $rcB = Invoke-Child $GitBash @('install.sh') $P1Clone (Join-Path $P1 'p1-b.log')
            $afterB = ''
            if (Test-Path -LiteralPath (Join-Path $P1Cfg 'CLAUDE.md')) { $afterB = (Get-Content -Raw -LiteralPath (Join-Path $P1Cfg 'CLAUDE.md')).Trim() }
            $rcC = Invoke-Child $PsHost $ps1Args $P1Clone (Join-Path $P1 'p1-c.log')
        } finally {
            Restore-Env 'CLAUDE_CONFIG_DIR' $savedCfg; Restore-Env 'HOME' $savedHome
        }
        Check "P1: ps1, sh and ps1 runs each exit 0 (exit $rcA, $rcB, $rcC)" ($rcA -eq 0 -and $rcB -eq 0 -and $rcC -eq 0)
        Check "P1: the sh run wrote its @~/ pointer, so the fixture reaches the flip (pointer after sh: $afterB)" ($afterB.StartsWith('@~/'))
        $baks = @(Get-ChildItem -LiteralPath $P1Cfg -Filter 'CLAUDE.md.bak.*' | ForEach-Object { $_.Name })
        Check "P1: ps1, sh, ps1 make no CLAUDE.md.bak (found $($baks.Count): $($baks -join ', '))" ($baks.Count -eq 0)
    }
} finally {
    Remove-Item -LiteralPath $P1 -Recurse -Force -ErrorAction SilentlyContinue
}

# ---- P3: a repeat run whose settings.json backup fails exits 1 and leaves settings.json as it was ---
# Copy mode is forced, so run 1 leaves a plain settings.json. Run 2 must back it up, which creates a
# new file in the config dir. A deny ACE on CreateFiles, on that dir only (no inheritance), makes the
# create fail. An in-place overwrite of the existing settings.json stays allowed, so an installer that
# refreshed settings.json before backing it up would change it. The ACL is restored before cleanup.
$P3 = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-p3-' + [guid]::NewGuid().ToString('N'))
try {
    $P3Clone = Join-Path $P3 'clone'
    $P3Cfg   = Join-Path $P3 'claude'
    New-Item -ItemType Directory -Force -Path $P3Clone, $P3Cfg | Out-Null
    Copy-Installer $P3Clone
    Write-Plain (Join-Path $P3Clone 'CLAUDE.md') "# p3 content`n"
    Write-Plain (Join-Path $P3Clone 'settings.json') "{`"src`": 1}`n"
    Write-Plain (Join-Path $P3Clone 'landed-dirs.txt') "skills`n"
    $ps1Args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $P3Clone 'install.ps1') + '"'))
    $savedCfg = $env:CLAUDE_CONFIG_DIR; $savedForce = $env:CLAUDE_SETTINGS_FORCE_COPY
    try {
        Assert-Scratch $P3Cfg $P3
        $env:CLAUDE_CONFIG_DIR = $P3Cfg; $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
        $rc1 = Invoke-Child $PsHost $ps1Args $P3Clone (Join-Path $P3 'p3-run1.log')
        Check "P3: run 1 (forced copy) exits 0 (exit $rc1)" ($rc1 -eq 0)
        $target = Join-Path $P3Cfg 'settings.json'
        $before = [IO.File]::ReadAllBytes($target)
        Write-Plain (Join-Path $P3Clone 'settings.json') "{`"src`": 2}`n"   # the source changes between runs
        $saved = Get-Acl -LiteralPath $P3Cfg
        $acl   = Get-Acl -LiteralPath $P3Cfg
        $sid   = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $rule  = New-Object Security.AccessControl.FileSystemAccessRule($sid, [Security.AccessControl.FileSystemRights]::CreateFiles, [Security.AccessControl.InheritanceFlags]::None, [Security.AccessControl.PropagationFlags]::None, [Security.AccessControl.AccessControlType]::Deny)
        $acl.AddAccessRule($rule)
        try {
            Set-Acl -LiteralPath $P3Cfg -AclObject $acl
            $newDenied = $false
            try { Write-Plain (Join-Path $P3Cfg 'p3-probe.tmp') 'x' } catch { $newDenied = $true }
            $overwriteOk = $true
            try { [IO.File]::WriteAllBytes($target, $before) } catch { $overwriteOk = $false }
            Check "P3: fixture deny blocks a new file in the config dir" $newDenied
            Check "P3: fixture deny leaves an in-place overwrite of settings.json working" $overwriteOk
            $rc2 = Invoke-Child $PsHost $ps1Args $P3Clone (Join-Path $P3 'p3-run2.log')
        } finally {
            Set-Acl -LiteralPath $P3Cfg -AclObject $saved
        }
        Check "P3: repeat run exits 1 when the settings.json backup fails (exit $rc2)" ($rc2 -eq 1)
        $after = [IO.File]::ReadAllBytes($target)
        Check "P3: settings.json is unchanged after the failed backup (still the run 1 copy)" ([Convert]::ToBase64String($after) -eq [Convert]::ToBase64String($before))
    } finally {
        Restore-Env 'CLAUDE_CONFIG_DIR' $savedCfg; Restore-Env 'CLAUDE_SETTINGS_FORCE_COPY' $savedForce
    }
} finally {
    Remove-Item -LiteralPath $P3 -Recurse -Force -ErrorAction SilentlyContinue
}

# ---- P4: the old janitor files leave bin\ on Windows (install.sh removes them today) ----------------
# The three exact names go. Decoys stay: a near name, a suffixed name, and a directory.
$P4 = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-p4-' + [guid]::NewGuid().ToString('N'))
try {
    $P4Clone = Join-Path $P4 'clone'
    $P4Cfg   = Join-Path $P4 'claude'
    $P4Bin   = Join-Path $P4Cfg 'bin'
    New-Item -ItemType Directory -Force -Path $P4Clone, $P4Bin | Out-Null
    Copy-Installer $P4Clone
    Write-Plain (Join-Path $P4Clone 'CLAUDE.md') "# p4 content`n"
    Write-Plain (Join-Path $P4Clone 'settings.json') "{}`n"
    Write-Plain (Join-Path $P4Clone 'landed-dirs.txt') "skills`n"
    foreach ($n in @('janitor.py', 'reap.py', 'session-teardown.sh', 'foo.sh', 'claude-janitor-old')) { Write-Plain (Join-Path $P4Bin $n) 'x' }
    New-Item -ItemType Directory -Force -Path (Join-Path $P4Bin 'janitor-dir') | Out-Null
    $savedCfg = $env:CLAUDE_CONFIG_DIR
    try {
        Assert-Scratch $P4Cfg $P4
        $env:CLAUDE_CONFIG_DIR = $P4Cfg
        $rc4 = Invoke-Child $PsHost @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $P4Clone 'install.ps1') + '"')) $P4Clone (Join-Path $P4 'p4.log')
        Check "P4: install.ps1 run exits 0 (exit $rc4)" ($rc4 -eq 0)
    } finally {
        Restore-Env 'CLAUDE_CONFIG_DIR' $savedCfg
    }
    $left = @(Get-ChildItem -LiteralPath $P4Bin -Force | ForEach-Object { $_.Name })
    $staleLeft = @($left | Where-Object { $_ -in @('janitor.py', 'reap.py', 'session-teardown.sh') })
    Check "P4: the three old janitor files are removed from bin\ (still present: $($staleLeft -join ', '))" ($staleLeft.Count -eq 0)
    $decoyGone = @(@('foo.sh', 'claude-janitor-old', 'janitor-dir') | Where-Object { $left -notcontains $_ })
    Check "P4: decoys are kept in bin\ (missing: $($decoyGone -join ', '))" ($decoyGone.Count -eq 0)
} finally {
    Remove-Item -LiteralPath $P4 -Recurse -Force -ErrorAction SilentlyContinue
}

# ---- P6: settings.json already linked, a later run still adds ~\.claude\bin to the PATH key -----
# Run 1 links settings.json (needs symlink rights, else SKIP). Run 2, on a fresh PATH key, must still
# add the bin dir. Today the already-linked branch exits before the PATH step. The log line shows run 2
# took that branch, so the case cannot pass on another path.
$p6Blocker = Get-LinkBlocker
if ($p6Blocker) {
    Write-Host "SKIP: P6 PATH after an existing link (no symlink rights: $p6Blocker)"
} else {
    $P6 = Join-Path ([IO.Path]::GetTempPath()) ('claude-settings-p6-' + [guid]::NewGuid().ToString('N'))
    try {
        $P6Clone = Join-Path $P6 'clone'
        $P6Cfg   = Join-Path $P6 'claude'
        New-Item -ItemType Directory -Force -Path $P6Clone, $P6Cfg | Out-Null
        Copy-Installer $P6Clone
        Write-Plain (Join-Path $P6Clone 'CLAUDE.md') "# p6 content`n"
        Write-Plain (Join-Path $P6Clone 'settings.json') "{}`n"
        Write-Plain (Join-Path $P6Clone 'landed-dirs.txt') "skills`n"
        $ps1Args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $P6Clone 'install.ps1') + '"'))
        $savedCfg = $env:CLAUDE_CONFIG_DIR; $savedKey = $env:CLAUDE_SETTINGS_USER_ENV_KEY
        try {
            Assert-Scratch $P6Cfg $P6
            $env:CLAUDE_CONFIG_DIR = $P6Cfg
            $env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$TestEnvSub\p6a"
            $rc6a = Invoke-Child $PsHost $ps1Args $P6Clone (Join-Path $P6 'p6-run1.log')
            $link = Get-Item -LiteralPath (Join-Path $P6Cfg 'settings.json') -Force -ErrorAction SilentlyContinue
            $linkedTo = ''
            if ($link -and $link.LinkType -eq 'SymbolicLink') { $linkedTo = [string](@($link.Target)[0]) }
            Check "P6: run 1 links settings.json to the clone's file (exit $rc6a, link target: '$linkedTo')" ($rc6a -eq 0 -and $linkedTo -eq (Join-Path $P6Clone 'settings.json'))

            $subB = "$TestEnvSub\p6b"
            [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($subB).Close()   # fresh key: no Path value yet
            $env:CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$subB"
            $log6b = Join-Path $P6 'p6-run2.log'
            $rc6b = Invoke-Child $PsHost $ps1Args $P6Clone $log6b
            $tookLinked = (Test-Path -LiteralPath $log6b) -and ((Get-Content -Raw -LiteralPath $log6b) -match 'already links to')
            Check "P6: run 2 took the already-linked branch (exit $rc6b)" ([bool]$tookLinked)
            $k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($subB)
            $pathVal = ''
            if ($k) { $pathVal = [string]$k.GetValue('Path', ''); $k.Close() }
            $binDir = Join-Path $env:USERPROFILE '.claude\bin'
            Check "P6: run 2 still adds $binDir to the PATH key (PATH key now: '$pathVal')" (($pathVal -split ';') -contains $binDir)
        } finally {
            Restore-Env 'CLAUDE_CONFIG_DIR' $savedCfg; Restore-Env 'CLAUDE_SETTINGS_USER_ENV_KEY' $savedKey
        }
    } finally {
        Remove-Item -LiteralPath $P6 -Recurse -Force -ErrorAction SilentlyContinue
    }
}

}

# ---- gap: the embedded post-merge hook body (install.ps1's Install-PostMergeHook) is not --
# covered here. It is a heredoc written into .git\hooks\post-merge and run by `git` itself on
# a real `git pull`, under `sh` inside Git Bash, not by any PowerShell function this file can
# load or call directly. Exercising it for real needs a real git repo, a real merge that
# changes install.ps1 or a skill, and a real Git-Bash `sh` to run the written hook body, none
# of which this harness drives. Reported as a gap, not faked.

} finally {
    if ($IsWin) { try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($TestEnvSub, $false) } catch { } }
    Remove-Item Env:\CLAUDE_SETTINGS_USER_ENV_KEY -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
