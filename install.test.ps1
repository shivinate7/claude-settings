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
# on Windows. Elsewhere each prints SKIP and the file goes on.

# True when $Path is a symlink or junction (a reparse point). A missing path is not a link.
function Test-ReparsePoint([string]$Path) {
    $i = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $i) { return $false }
    return (([int]$i.Attributes) -band [int][IO.FileAttributes]::ReparsePoint) -ne 0
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
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Co 'install.ps1')
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
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Co3 'install.ps1')
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
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    & $PsHost -NoProfile -File (Join-Path $Co4 'install.ps1') *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: firstinstall1 run 1 exited $LASTEXITCODE"; $Failed++ }

    $SkillBaks1 = @(Get-ChildItem -Path (Join-Path (Join-Path $Cfg4 'backups') 'skills') -Filter 'sample-skill.*' -ErrorAction SilentlyContinue)
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

    $SkillBaks2 = @(Get-ChildItem -Path (Join-Path (Join-Path $Cfg4 'backups') 'skills') -Filter 'sample-skill.*' -ErrorAction SilentlyContinue)
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
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $Co5 'install.ps1')
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
# ---- refusewt1 / keepwt1: a linked worktree stops install.ps1; the main clone still installs ----
# An install from a linked worktree would point ~\.claude at that temp checkout. From a linked
# worktree install.ps1 must exit non-zero, print a line that names the main clone, and write nothing:
# the config dir and the fake USERPROFILE stay as they were. keepwt1 guards the other
# side: the main clone of a repo that has a linked worktree still installs. Plain folder copies with
# no .git are already covered by the copymode, settingsrepeat, firstinstall and envkey cases above.
# Each child run gets its own fake USERPROFILE, CLAUDE_CONFIG_DIR and throwaway PATH key.

# Get-TreeSnapshot DIR: one line per entry under DIR (relative path and size); '<absent>' if DIR is missing.
function Get-TreeSnapshot([string]$Dir) {
    if (-not (Test-Path -LiteralPath $Dir)) { return '<absent>' }
    $root = (Resolve-Path -LiteralPath $Dir).Path
    return ((Get-ChildItem -LiteralPath $Dir -Recurse -Force | ForEach-Object { $_.FullName.Substring($root.Length) + '|' + $_.Length }) -join "`n")
}

# New-WtFixture ROOT: a git repo at ROOT\main with one detached linked worktree at ROOT\wt. Both hold
# an install.ps1 copy (untracked, so the worktree gets it by copy, not by commit). Returns @{ Main; Wt },
# or $null when git cannot make the worktree.
function New-WtFixture([string]$Root) {
    $main = Join-Path $Root 'main'
    $wt   = Join-Path $Root 'wt'
    New-Item -ItemType Directory -Force -Path $main | Out-Null
    Set-Content -Path (Join-Path $main 'CLAUDE.md') -Value '# wt fixture content' -Encoding utf8
    Set-Content -Path (Join-Path $main 'settings.json') -Value '{}' -Encoding utf8
    Set-Content -Path (Join-Path $main 'landed-dirs.txt') -Value 'skills' -Encoding utf8
    $sk = Join-Path $main 'skills\sample-skill'
    New-Item -ItemType Directory -Force -Path $sk | Out-Null
    Set-Content -Path (Join-Path $sk 'SKILL.md') -Value 'v1' -Encoding utf8
    git -C $main init -q -b main | Out-Null
    git -C $main add -A | Out-Null
    git -C $main -c user.email=t@example.com -c user.name=t commit -q -m init | Out-Null
    git -C $main worktree add -q --detach $wt | Out-Null
    if ($LASTEXITCODE -ne 0) { return $null }
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $main 'install.ps1')
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $wt 'install.ps1')
    return @{ Main = $main; Wt = $wt }
}

# Invoke-InstallProc INSTALL_PS1 CFG FAKE_HOME LOGDIR: runs install.ps1 in a child host. The three
# variables are set for the child only and restored after. Returns @{ Exit; Text } (stdout, then stderr).
# Start-Process keeps stderr out of the PowerShell error stream, so Stop does not turn a line into an error.
function Invoke-InstallProc([string]$InstallPs1, [string]$Cfg, [string]$FakeHome, [string]$LogDir) {
    $names = @('CLAUDE_CONFIG_DIR', 'USERPROFILE', 'CLAUDE_SETTINGS_USER_ENV_KEY')
    $saved = @{}
    foreach ($n in $names) { $saved[$n] = [Environment]::GetEnvironmentVariable($n) }
    try {
        [Environment]::SetEnvironmentVariable('CLAUDE_CONFIG_DIR', $Cfg)
        [Environment]::SetEnvironmentVariable('USERPROFILE', $FakeHome)
        [Environment]::SetEnvironmentVariable('CLAUDE_SETTINGS_USER_ENV_KEY', "HKCU:\$TestEnvSub\" + (Split-Path -Leaf $FakeHome))
        $outFile = Join-Path $LogDir 'stdout.txt'
        $errFile = Join-Path $LogDir 'stderr.txt'
        $p = Start-Process -FilePath $PsHost -ArgumentList @('-NoProfile', '-File', ('"' + $InstallPs1 + '"')) -Wait -PassThru -NoNewWindow -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        $text = (@(Get-Content -LiteralPath $outFile -ErrorAction SilentlyContinue) + @(Get-Content -LiteralPath $errFile -ErrorAction SilentlyContinue)) -join "`n"
        return @{ Exit = $p.ExitCode; Text = $text }
    } finally {
        foreach ($n in $names) { [Environment]::SetEnvironmentVariable($n, $saved[$n]) }
    }
}

$RwRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-refusewt-" + [guid]::NewGuid().ToString('N'))
$RwHome = Join-Path $RwRoot 'home'
$RwCfg  = Join-Path $RwRoot 'claude'
$RwLogs = Join-Path $RwRoot 'logs'
New-Item -ItemType Directory -Force -Path $RwHome, $RwCfg, $RwLogs | Out-Null
try {
    $rwFix = New-WtFixture (Join-Path $RwRoot 'repo')
    if (-not $rwFix) {
        Write-Host "FAIL: refusewt1 fixture: git worktree add failed"; $Failed++
    } else {
        # Seed the config dir with a pointer to the main clone, as an earlier install would have.
        $RwPtr = Join-Path $RwCfg 'CLAUDE.md'
        [IO.File]::WriteAllText($RwPtr, ('@' + ($rwFix.Main -replace '\\', '/').TrimEnd('/') + '/CLAUDE.md'), [Text.UTF8Encoding]::new($false))
        $ptrBefore  = [IO.File]::ReadAllText($RwPtr)
        $snapBefore = Get-TreeSnapshot $RwCfg
        $rwRes = Invoke-InstallProc (Join-Path $rwFix.Wt 'install.ps1') $RwCfg $RwHome $RwLogs
        $named = @($rwRes.Text -split "`n" | Where-Object { $_ -match '(?i)main clone' }).Count
        Check "refusewt1: install.ps1 run from a linked worktree exits non-zero" ($rwRes.Exit -ne 0)
        Check "refusewt1: it prints a line that names the main clone" ($named -ge 1)
        $wrote = @()
        if ([IO.File]::ReadAllText($RwPtr) -ne $ptrBefore) { $wrote += 'pointer rewritten' }
        if ((Get-TreeSnapshot $RwCfg) -ne $snapBefore) { $wrote += 'config dir changed' }
        # A bare child PowerShell creates AppData\Roaming under its USERPROFILE on start, so that folder is
        # the host's, not the installer's. Any other entry in the fake home is a write.
        $stray = @(Get-ChildItem -LiteralPath $RwHome -Force | Where-Object { $_.Name -ne 'AppData' })
        if ($stray.Count) { $wrote += 'fake USERPROFILE written' }
        Check "refusewt1: writes nothing (pointer kept, config dir and fake USERPROFILE unchanged)" ($wrote.Count -eq 0)
        if ($wrote.Count) { Write-Host "  refusewt1 wrote: $($wrote -join '; ')" }
    }
} finally {
    Remove-Item -Recurse -Force $RwRoot -ErrorAction SilentlyContinue
}

$KwRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-keepwt-" + [guid]::NewGuid().ToString('N'))
$KwHome = Join-Path $KwRoot 'home'
$KwCfg  = Join-Path $KwRoot 'claude'
$KwLogs = Join-Path $KwRoot 'logs'
New-Item -ItemType Directory -Force -Path $KwHome, $KwLogs | Out-Null
try {
    $kwFix = New-WtFixture (Join-Path $KwRoot 'repo')
    if (-not $kwFix) {
        Write-Host "FAIL: keepwt1 fixture: git worktree add failed"; $Failed++
    } else {
        $kwRes  = Invoke-InstallProc (Join-Path $kwFix.Main 'install.ps1') $KwCfg $KwHome $KwLogs
        $kwPtr  = Join-Path $KwCfg 'CLAUDE.md'
        $kwWant = '@' + (($kwFix.Main + '-live') -replace '\\', '/').TrimEnd('/') + '/CLAUDE.md'
        $kwGot  = if (Test-Path -LiteralPath $kwPtr) { [IO.File]::ReadAllText($kwPtr).TrimStart([char]0xFEFF).Trim() } else { '' }
        Check "keepwt1: main clone of a repo with a linked worktree exits 0" ($kwRes.Exit -eq 0)
        Check "keepwt1: that run points the config CLAUDE.md at the pinned checkout <clone>-live" ($kwGot -eq $kwWant)
        if ($kwRes.Exit -ne 0) { Write-Host "  keepwt1 output: $($kwRes.Text)" }
    }
} finally {
    Remove-Item -Recurse -Force $KwRoot -ErrorAction SilentlyContinue
}
# ---- pinnedps1 / pinnedwt1: the pinned checkout at <clone>-live --------------------------------
# Per merge-reinstalls-from-main, the links in ~\.claude point at one pinned
# checkout, a worktree of the clone on a detached HEAD at main's commit, at the sibling path
# <clone>-live. pinnedps1: with none present, install.ps1 run from the clone makes it at main's
# commit, and the config CLAUDE.md pointer names it. pinnedwt1: the linked-worktree guard lets
# install.ps1 run from that path, and from no other linked worktree (refusewt1 keeps that side).
# Each run is a child host with a fake USERPROFILE, a fake CLAUDE_CONFIG_DIR
# and the throwaway PATH key, as envkey1 does.

# New-PinFixture ROOT: a git clone at ROOT\clone on branch main, with one commit that holds
# install.ps1, CLAUDE.md, settings.json, landed-dirs.txt and one skill. Returns the clone path.
function New-PinFixture([string]$Root) {
    $main = Join-Path $Root 'clone'
    New-Item -ItemType Directory -Force -Path $main | Out-Null
    Set-Content -Path (Join-Path $main 'CLAUDE.md') -Value '# pinned fixture content' -Encoding utf8
    Set-Content -Path (Join-Path $main 'settings.json') -Value '{}' -Encoding utf8
    Set-Content -Path (Join-Path $main 'landed-dirs.txt') -Value 'skills' -Encoding utf8
    $sk = Join-Path $main 'skills\sample-skill'
    New-Item -ItemType Directory -Force -Path $sk | Out-Null
    Set-Content -Path (Join-Path $sk 'SKILL.md') -Value 'v1' -Encoding utf8
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $main 'install.ps1')
    git -C $main init -q -b main | Out-Null
    git -C $main add -A | Out-Null
    git -C $main -c user.email=t@example.com -c user.name=t commit -q -m init | Out-Null
    return $main
}

$PnRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-pinnedps1-" + [guid]::NewGuid().ToString('N'))
$PnHome = Join-Path $PnRoot 'home'
$PnCfg  = Join-Path $PnRoot 'claude'
$PnLogs = Join-Path $PnRoot 'logs'
New-Item -ItemType Directory -Force -Path $PnHome, $PnLogs | Out-Null
try {
    $pnMain = New-PinFixture $PnRoot
    $pnPin  = $pnMain + '-live'
    $pnHead = (& git -C $pnMain rev-parse HEAD).Trim()
    $pnRes  = Invoke-InstallProc (Join-Path $pnMain 'install.ps1') $PnCfg $PnHome $PnLogs
    $pnWant = '@' + ($pnPin -replace '\\', '/').TrimEnd('/') + '/CLAUDE.md'
    $pnPtr  = Join-Path $PnCfg 'CLAUDE.md'
    $pnGot  = if (Test-Path -LiteralPath $pnPtr) { [IO.File]::ReadAllText($pnPtr).TrimStart([char]0xFEFF).Trim() } else { '' }
    $pnHere = Test-Path -LiteralPath $pnPin
    $pnAt   = if ($pnHere) { (& git -C $pnPin rev-parse HEAD).Trim() } else { '' }
    $pnRef  = if ($pnHere) { (& git -C $pnPin rev-parse --symbolic-full-name HEAD).Trim() } else { '' }
    Check "pinnedps1: install.ps1 run from the clone exits 0" ($pnRes.Exit -eq 0)
    Check "pinnedps1: it makes a pinned checkout at <clone>-live" $pnHere
    Check "pinnedps1: the pinned checkout is at main's commit" ($pnAt -eq $pnHead)
    Check "pinnedps1: the pinned checkout is on a detached HEAD" ($pnRef -eq 'HEAD')
    Check "pinnedps1: the config CLAUDE.md pointer names the pinned checkout" ($pnGot -eq $pnWant)
    if ($pnRes.Exit -ne 0) { Write-Host "  pinnedps1 output: $($pnRes.Text)" }
} finally {
    Remove-Item -Recurse -Force $PnRoot -ErrorAction SilentlyContinue
}

$PwRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-pinnedwt-" + [guid]::NewGuid().ToString('N'))
$PwHome = Join-Path $PwRoot 'home'
$PwCfg  = Join-Path $PwRoot 'claude'
$PwLogs = Join-Path $PwRoot 'logs'
New-Item -ItemType Directory -Force -Path $PwHome, $PwLogs | Out-Null
try {
    $pwMain = New-PinFixture $PwRoot
    $pwPin  = $pwMain + '-live'
    git -C $pwMain worktree add -q --detach $pwPin | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: pinnedwt1 fixture: git worktree add failed"; $Failed++
    } else {
        $pwRes  = Invoke-InstallProc (Join-Path $pwPin 'install.ps1') $PwCfg $PwHome $PwLogs
        $pwWant = '@' + ($pwPin -replace '\\', '/').TrimEnd('/') + '/CLAUDE.md'
        $pwPtr  = Join-Path $PwCfg 'CLAUDE.md'
        $pwGot  = if (Test-Path -LiteralPath $pwPtr) { [IO.File]::ReadAllText($pwPtr).TrimStart([char]0xFEFF).Trim() } else { '' }
        Check "pinnedwt1: install.ps1 run from <clone>-live is not refused and exits 0" ($pwRes.Exit -eq 0)
        Check "pinnedwt1: that run points the config CLAUDE.md at the pinned checkout" ($pwGot -eq $pwWant)
        if ($pwRes.Exit -ne 0) { Write-Host "  pinnedwt1 output: $($pwRes.Text)" }
    }
} finally {
    Remove-Item -Recurse -Force $PwRoot -ErrorAction SilentlyContinue
}

# ---- pinlive cases: <clone>-live is the one linked worktree allowed, and only at local main ----
# Per merge-reinstalls-from-main, install.ps1 allows a linked worktree only at
# <clone>-live AND detached at the clone's local main commit. pinlivewt1: a -live worktree on a lane
# branch is refused. pinlivewt2: a -live worktree detached at a commit that is not main is refused.
# pinlivehook1: run from the pin, the post-merge hook still lands in the clone's .git\hooks. Only copy
# mode calls Install-PostMergeHook, so the case forces it and checks the settings.json copy first.
# pinlivestale1: a -live folder deleted but still registered; the failure line carries git's own
# message or names the stale registration. pinnedwt1 keeps detached-at-main passing.

# Set-PinLivePointer CFG TARGET: the config CLAUDE.md pointer an earlier install would have left.
function Set-PinLivePointer([string]$Cfg, [string]$Target) {
    New-Item -ItemType Directory -Force -Path $Cfg | Out-Null
    $ptr = '@' + ($Target -replace '\\', '/').TrimEnd('/') + '/CLAUDE.md'
    [IO.File]::WriteAllText((Join-Path $Cfg 'CLAUDE.md'), $ptr, [Text.UTF8Encoding]::new($false))
}

# Get-PinLiveListing DIR: every path under DIR, sorted, as one string. Compared before and after a run.
function Get-PinLiveListing([string]$Dir) {
    (Get-ChildItem -LiteralPath $Dir -Recurse -Force | ForEach-Object { $_.FullName } | Sort-Object) -join "`n"
}

$LwRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-pinlivewt1-" + [guid]::NewGuid().ToString('N'))
$LwHome = Join-Path $LwRoot 'home'
$LwCfg  = Join-Path $LwRoot 'claude'
$LwLogs = Join-Path $LwRoot 'logs'
New-Item -ItemType Directory -Force -Path $LwHome, $LwLogs | Out-Null
try {
    $lwMain = New-PinFixture $LwRoot
    $lwPin  = $lwMain + '-live'
    git -C $lwMain worktree add -q -b lane $lwPin | Out-Null
    $lwBranch = (& git -C $lwPin symbolic-ref -q --short HEAD)
    if ($LASTEXITCODE -ne 0 -or $lwBranch -ne 'lane') {
        Write-Host "FAIL: pinlivewt1 fixture: the pinned path is not on branch lane"; $Failed++
    } else {
        Set-PinLivePointer $LwCfg $lwMain
        $lwPtr  = Join-Path $LwCfg 'CLAUDE.md'
        $lwWas  = [IO.File]::ReadAllText($lwPtr)
        $lwSnap = Get-PinLiveListing $LwCfg
        $lwRes  = Invoke-InstallProc (Join-Path $lwPin 'install.ps1') $LwCfg $LwHome $LwLogs
        $lwNow  = [IO.File]::ReadAllText($lwPtr)
        Check "pinlivewt1: install.ps1 run from <clone>-live on a lane branch exits non-zero" ($lwRes.Exit -ne 0)
        Check "pinlivewt1: the refused run leaves the config CLAUDE.md pointer unchanged" ($lwNow -eq $lwWas)
        Check "pinlivewt1: the refused run writes nothing under the config dir" ((Get-PinLiveListing $LwCfg) -eq $lwSnap)
        if ($lwRes.Exit -eq 0) { Write-Host "  pinlivewt1 output: $($lwRes.Text)" }
    }
} finally {
    Remove-Item -Recurse -Force $LwRoot -ErrorAction SilentlyContinue
}

$LoRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-pinlivewt2-" + [guid]::NewGuid().ToString('N'))
$LoHome = Join-Path $LoRoot 'home'
$LoCfg  = Join-Path $LoRoot 'claude'
$LoLogs = Join-Path $LoRoot 'logs'
New-Item -ItemType Directory -Force -Path $LoHome, $LoLogs | Out-Null
try {
    $loMain = New-PinFixture $LoRoot
    $loPin  = $loMain + '-live'
    git -C $loMain worktree add -q --detach $loPin | Out-Null
    # The pin stays at the old main; main then moves on, as it does between a merge and the move.
    Add-Content -LiteralPath (Join-Path $loMain 'CLAUDE.md') -Value 'second' -Encoding ascii
    git -C $loMain add -A | Out-Null
    git -C $loMain -c user.email=t@example.com -c user.name=t commit -q -m second | Out-Null
    $loAt     = (& git -C $loPin rev-parse HEAD).Trim()
    $loMainAt = (& git -C $loMain rev-parse refs/heads/main).Trim()
    if ($LASTEXITCODE -ne 0 -or $loAt -eq $loMainAt) {
        Write-Host "FAIL: pinlivewt2 fixture: the pinned checkout did not stay behind main"; $Failed++
    } else {
        Set-PinLivePointer $LoCfg $loMain
        $loPtr  = Join-Path $LoCfg 'CLAUDE.md'
        $loWas  = [IO.File]::ReadAllText($loPtr)
        $loSnap = Get-PinLiveListing $LoCfg
        $loRes  = Invoke-InstallProc (Join-Path $loPin 'install.ps1') $LoCfg $LoHome $LoLogs
        $loNow  = [IO.File]::ReadAllText($loPtr)
        Check "pinlivewt2: install.ps1 run from <clone>-live detached off main exits non-zero" ($loRes.Exit -ne 0)
        Check "pinlivewt2: the refused run leaves the config CLAUDE.md pointer unchanged" ($loNow -eq $loWas)
        Check "pinlivewt2: the refused run writes nothing under the config dir" ((Get-PinLiveListing $LoCfg) -eq $loSnap)
        if ($loRes.Exit -eq 0) { Write-Host "  pinlivewt2 output: $($loRes.Text)" }
    }
} finally {
    Remove-Item -Recurse -Force $LoRoot -ErrorAction SilentlyContinue
}

$LhRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-pinlivehook1-" + [guid]::NewGuid().ToString('N'))
$LhHome = Join-Path $LhRoot 'home'
$LhCfg  = Join-Path $LhRoot 'claude'
$LhLogs = Join-Path $LhRoot 'logs'
New-Item -ItemType Directory -Force -Path $LhHome, $LhLogs | Out-Null
try {
    $lhMain = New-PinFixture $LhRoot
    $lhPin  = $lhMain + '-live'
    git -C $lhMain worktree add -q --detach $lhPin | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: pinlivehook1 fixture: git worktree add failed"; $Failed++
    } else {
        $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
        try { $lhRes = Invoke-InstallProc (Join-Path $lhPin 'install.ps1') $LhCfg $LhHome $LhLogs }
        finally { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
        $lhSet  = Join-Path $LhCfg 'settings.json'
        $lhHook = Join-Path $lhMain '.git\hooks\post-merge'
        $lhGot  = if (Test-Path -LiteralPath $lhHook) { [IO.File]::ReadAllText($lhHook) } else { '' }
        Check "pinlivehook1 fixture: settings.json is a copy, so copy mode ran" ((Test-Path -LiteralPath $lhSet) -and -not (Test-ReparsePoint $lhSet))
        Check "pinlivehook1: install.ps1 run from <clone>-live exits 0" ($lhRes.Exit -eq 0)
        Check "pinlivehook1: the post-merge hook lands in the clone's .git\hooks" ($lhGot.Contains('# claude-settings post-merge hook'))
        if ($lhRes.Exit -ne 0) { Write-Host "  pinlivehook1 output: $($lhRes.Text)" }
    }
} finally {
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $LhRoot -ErrorAction SilentlyContinue
}

# ---- hookgone / hookkeep / hookwrite: the git post-merge hook install.ps1 keeps only for copy mode ----
# Owner ruling 2026-10-22 (stale-postmerge-hook): when symlinks work, install.ps1 removes its own
# post-merge hook, the one that carries the marker line, and the install log's hook= field says
# `removed`. A post-merge hook without the marker is not ours and stays byte for byte. When symlinks
# fail, the marked hook is still written.
# hookgone1: the run that makes the links. hookgone1b: a rerun over links already made, the early exit
# a machine that installed once takes every time. hookkeep1: an unmarked hook, both runs. hookwrite1:
# copy mode, forced, over a stale marked hook. hookkeep1 and hookwrite1 pass on a build without the
# removal; they go red if the removal is too wide or runs in copy mode.
# hookkeepagents1: links for settings.json but a copied skill, so the hook stays (decision
# post-merge-hook-is-a-fallback, copied files keep refreshing); hookkeepagents1b is the rerun.
# hookgonefail1: a marked hook that cannot be deleted must not stop the run summary line, and the
# install log must say the delete failed.
# Link mode needs symlink rights. The run itself is the probe: a settings.json that is no link after it
# prints SKIP, unknown and not red. hookgone and hookkeep clear CLAUDE_SETTINGS_FORCE_COPY, so a
# copy-mode run cannot stand in for a link run.

$HookMarker = '# claude-settings post-merge hook'
$HookUtf8   = [Text.UTF8Encoding]::new($false)

# Set-HookFile CLONE BYTES: the post-merge hook of the git clone at CLONE.
function Set-HookFile([string]$Clone, [byte[]]$Bytes) {
    $d = Join-Path $Clone '.git\hooks'
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $d 'post-merge'), $Bytes)
}

# Get-HookFileText CLONE: the hook's text, or $null when there is none.
function Get-HookFileText([string]$Clone) {
    $p = Join-Path $Clone '.git\hooks\post-merge'
    if (Test-Path -LiteralPath $p) { return [IO.File]::ReadAllText($p) }
    return $null
}

# Get-InstallLogHookMode CFG: the hook= value on the last run summary line of CFG's install log, or $null.
function Get-InstallLogHookMode([string]$Cfg) {
    $lp = Join-Path $Cfg 'claude-settings-install.log'
    if (-not (Test-Path -LiteralPath $lp)) { return $null }
    $line = @(Get-Content -LiteralPath $lp | Where-Object { $_ -match 'install\.ps1: settings\.json=' }) | Select-Object -Last 1
    if ($line -and $line -match 'hook=(.*)$') { return $Matches[1].Trim() }
    return $null
}

# Get-InstallLogLines CFG: every line of CFG's install log, or an empty array.
function Get-InstallLogLines([string]$Cfg) {
    $lp = Join-Path $Cfg 'claude-settings-install.log'
    if (-not (Test-Path -LiteralPath $lp)) { return @() }
    return @(Get-Content -LiteralPath $lp)
}

# Get-InstallLogStampProblems LINES PREFIX OFFSET: one string per problem in LINES, the install log lines that
# name PREFIX (e.g. 'install.ps1:'). Each must start with yyyy-MM-ddTHH:mm:ss, a sign, HH:mm and a space,
# and carry the offset OFFSET. An empty result means every line holds.
# Its shell twin is stamp_problems in hooks/test_install_src.sh: a PowerShell case cannot call that step.
function Get-InstallLogStampProblems([string[]]$Lines, [string]$Prefix, [string]$Offset) {
    $named = @($Lines | Where-Object { $_.Contains($Prefix) })
    if ($named.Count -eq 0) { return @("no line of the install log names $Prefix") }
    $problems = @()
    foreach ($l in $named) {
        if ($l -notmatch '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d ') { $problems += "no offset stamp: $l"; continue }
        if ($l.Substring(19, 6) -ne $Offset) { $problems += "offset $($l.Substring(19, 6)), want ${Offset}: $l" }
    }
    return @($problems)
}

# Add-NoSubdirRule DIR: deny the current user the right to make a sub-directory in DIR. A directory
# symlink is a sub-directory, so the link try fails there, while a file in DIR, a link in any other
# folder, and a copy into a directory that already exists in DIR all still work. That makes a skill
# copy while settings.json links, in one run, without a change to install.ps1. Returns the rule;
# hand it to Remove-NoSubdirRule before the folder is deleted.
function Add-NoSubdirRule([string]$Dir) {
    $sid  = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, [Security.AccessControl.FileSystemRights]::CreateDirectories, [Security.AccessControl.InheritanceFlags]::None, [Security.AccessControl.PropagationFlags]::None, [Security.AccessControl.AccessControlType]::Deny)
    $acl = Get-Acl -LiteralPath $Dir
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Dir -AclObject $acl
    return $rule
}
function Remove-NoSubdirRule([string]$Dir, $Rule) {
    $acl = Get-Acl -LiteralPath $Dir
    [void]$acl.RemoveAccessRuleSpecific($Rule)
    Set-Acl -LiteralPath $Dir -AclObject $acl
}

$HgRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-hookgone1-" + [guid]::NewGuid().ToString('N'))
$HgHome = Join-Path $HgRoot 'home'
$HgCfg  = Join-Path $HgRoot 'claude'
$HgLogs = Join-Path $HgRoot 'logs'
New-Item -ItemType Directory -Force -Path $HgHome, $HgLogs | Out-Null
try {
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    $hgMain  = New-PinFixture $HgRoot
    $hgSet   = Join-Path $HgCfg 'settings.json'
    $hgStale = $HookUtf8.GetBytes("#!/bin/sh`n$HookMarker`n# stale body`nexit 0`n")
    foreach ($hgRun in @(@{ Name = 'hookgone1'; Say = 'first run, which makes the links' }, @{ Name = 'hookgone1b'; Say = 'rerun over links already made' })) {
        Set-HookFile $hgMain $hgStale
        $hgRes    = Invoke-InstallProc (Join-Path $hgMain 'install.ps1') $HgCfg $HgHome $HgLogs
        $hgLinked = Test-ReparsePoint $hgSet
        if (-not $hgLinked) {
            Write-Host "SKIP: $($hgRun.Name): settings.json is no link after the run, so this account cannot make symlinks (unknown, not red)"
            break
        }
        $hgText = Get-HookFileText $hgMain
        $hgMode = Get-InstallLogHookMode $HgCfg
        Check "$($hgRun.Name) fixture: settings.json is a link, so link mode ran ($($hgRun.Say))" $hgLinked
        Check "$($hgRun.Name): install.ps1 exits 0" ($hgRes.Exit -eq 0)
        Check "$($hgRun.Name): the marked post-merge hook is gone from the clone's .git\hooks" ($null -eq $hgText)
        Check "$($hgRun.Name): the install log's hook= field says removed" ($hgMode -eq 'removed')
        if ($null -ne $hgText -or $hgMode -ne 'removed') { Write-Host "  $($hgRun.Name): hook file present: $($null -ne $hgText); log hook= '$hgMode'" }
        if ($hgRes.Exit -ne 0) { Write-Host "  $($hgRun.Name) output: $($hgRes.Text)" }
    }
} finally {
    Remove-Item -Recurse -Force $HgRoot -ErrorAction SilentlyContinue
}

$HkRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-hookkeep1-" + [guid]::NewGuid().ToString('N'))
$HkHome = Join-Path $HkRoot 'home'
$HkCfg  = Join-Path $HkRoot 'claude'
$HkLogs = Join-Path $HkRoot 'logs'
New-Item -ItemType Directory -Force -Path $HkHome, $HkLogs | Out-Null
try {
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    $hkMain = New-PinFixture $HkRoot
    $hkSet  = Join-Path $HkCfg 'settings.json'
    # A Git LFS style hook: a shell hook, no marker, a CR inside and no final newline, so a rewrite shows.
    $hkOwn  = $HookUtf8.GetBytes("#!/bin/sh`ncommand -v git-lfs >/dev/null 2>&1 || exit 2`r`ngit lfs post-merge `"`$@`"")
    $hkWant = [Convert]::ToBase64String($hkOwn)
    Set-HookFile $hkMain $hkOwn
    foreach ($hkName in 'hookkeep1', 'hookkeep1b') {
        $hkRes    = Invoke-InstallProc (Join-Path $hkMain 'install.ps1') $HkCfg $HkHome $HkLogs
        $hkLinked = Test-ReparsePoint $hkSet
        if (-not $hkLinked) {
            Write-Host "SKIP: ${hkName}: settings.json is no link after the run, so this account cannot make symlinks (unknown, not red)"
            break
        }
        $hkPath = Join-Path $hkMain '.git\hooks\post-merge'
        $hkGot  = if (Test-Path -LiteralPath $hkPath) { [Convert]::ToBase64String([IO.File]::ReadAllBytes($hkPath)) } else { '' }
        Check "$hkName fixture: settings.json is a link, so link mode ran" $hkLinked
        Check "${hkName}: install.ps1 exits 0" ($hkRes.Exit -eq 0)
        Check "${hkName}: a post-merge hook without the marker stays, byte for byte" ($hkGot -eq $hkWant)
        Check "${hkName}: the install log's hook= field does not state a removal" ((Get-InstallLogHookMode $HkCfg) -ne 'removed')
        if ($hkRes.Exit -ne 0) { Write-Host "  $hkName output: $($hkRes.Text)" }
    }
} finally {
    Remove-Item -Recurse -Force $HkRoot -ErrorAction SilentlyContinue
}

# hookkeepagents1: settings.json links but a skill is copied (the skills\ folder refuses a directory
# link, see Add-NoSubdirRule), so the copy still needs the hook to refresh it after a pull. The marked
# hook stays, rewritten, and the log says hook=installed. hookkeepagents1b is the rerun, the early exit.
# The cfg holds an earlier copy of the skill and the install marker, so the run is a repeat install:
# it refreshes that copy in place and makes no .bak.
$KaRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-hookkeepagents1-" + [guid]::NewGuid().ToString('N'))
$KaHome = Join-Path $KaRoot 'home'
$KaCfg  = Join-Path $KaRoot 'claude'
$KaLogs = Join-Path $KaRoot 'logs'
$KaSkills = Join-Path $KaCfg 'skills'
$KaSkill  = Join-Path $KaSkills 'sample-skill'
New-Item -ItemType Directory -Force -Path $KaHome, $KaLogs, $KaSkill | Out-Null
$KaRule = $null
try {
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    $kaMain = New-PinFixture $KaRoot
    $kaSet  = Join-Path $KaCfg 'settings.json'
    Set-Content -Path (Join-Path $KaSkill 'SKILL.md') -Value 'v0' -Encoding utf8
    [IO.File]::WriteAllText((Join-Path $KaCfg '.claude-settings-installed'), '')
    $kaStale = $HookUtf8.GetBytes("#!/bin/sh`n$HookMarker`n# stale body`nexit 0`n")
    try { $KaRule = Add-NoSubdirRule $KaSkills } catch { Write-Host "  hookkeepagents1: the deny rule on skills\ failed: $($_.Exception.Message)" }
    if (-not $KaRule) {
        Check "hookkeepagents1 fixture: a deny rule on skills\ blocks directory links" $false
    } else {
        foreach ($kaName in 'hookkeepagents1', 'hookkeepagents1b') {
            Set-HookFile $kaMain $kaStale
            $kaRes    = Invoke-InstallProc (Join-Path $kaMain 'install.ps1') $KaCfg $KaHome $KaLogs
            $kaLinked = Test-ReparsePoint $kaSet
            if (-not $kaLinked) {
                Write-Host "SKIP: ${kaName}: settings.json is no link after the run, so this account cannot make symlinks (unknown, not red)"
                break
            }
            $kaText = Get-HookFileText $kaMain
            $kaMode = Get-InstallLogHookMode $KaCfg
            Check "$kaName fixture: settings.json is a link, so link mode ran" $kaLinked
            Check "$kaName fixture: skills\sample-skill is a real directory, so the skill was copied" ((Test-Path -LiteralPath $KaSkill -PathType Container) -and -not (Test-ReparsePoint $KaSkill))
            Check "${kaName}: install.ps1 exits 0" ($kaRes.Exit -eq 0)
            Check "${kaName}: the marked post-merge hook stays in the clone's .git\hooks" ($null -ne $kaText -and $kaText.Contains($HookMarker))
            Check "${kaName}: the install log's hook= field says installed" ($kaMode -eq 'installed')
            if ($null -eq $kaText -or $kaMode -ne 'installed') { Write-Host "  ${kaName}: hook file present: $($null -ne $kaText); log hook= '$kaMode'" }
            if ($kaRes.Exit -ne 0) { Write-Host "  $kaName output: $($kaRes.Text)" }
        }
    }
} finally {
    if ($KaRule) { try { Remove-NoSubdirRule $KaSkills $KaRule } catch { Write-Host "  hookkeepagents1: could not remove the deny rule on ${KaSkills}: $($_.Exception.Message)" } }
    Remove-Item -Recurse -Force $KaRoot -ErrorAction SilentlyContinue
}

# hookgonefail1: links work and the marked hook cannot be deleted. install.ps1 must still write its run
# summary line, and the install log must name the hook and say the delete failed. The hook is held open
# with no delete share, the way a git or an editor handle on it would be. Read-only would not do:
# Remove-Item -Force clears that flag. Read share stays on, so install.ps1 can still read the marker.
$HfRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-hookgonefail1-" + [guid]::NewGuid().ToString('N'))
$HfHome = Join-Path $HfRoot 'home'
$HfCfg  = Join-Path $HfRoot 'claude'
$HfLogs = Join-Path $HfRoot 'logs'
New-Item -ItemType Directory -Force -Path $HfHome, $HfLogs | Out-Null
$HfHold = $null
try {
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    $hfMain = New-PinFixture $HfRoot
    $hfSet  = Join-Path $HfCfg 'settings.json'
    Set-HookFile $hfMain ($HookUtf8.GetBytes("#!/bin/sh`n$HookMarker`n# stale body`nexit 0`n"))
    $HfHold = [IO.File]::Open((Join-Path $hfMain '.git\hooks\post-merge'), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try { $hfRes = Invoke-InstallProc (Join-Path $hfMain 'install.ps1') $HfCfg $HfHome $HfLogs }
    finally { $HfHold.Dispose(); $HfHold = $null }
    $hfLinked = Test-ReparsePoint $hfSet
    $hfText   = Get-HookFileText $hfMain
    $hfMode   = Get-InstallLogHookMode $HfCfg
    $hfLines  = @(Get-InstallLogLines $HfCfg)
    if (-not $hfLinked) {
        Write-Host "SKIP: hookgonefail1: settings.json is no link after the run, so this account cannot make symlinks (unknown, not red)"
    } elseif ($null -eq $hfText) {
        Write-Host "SKIP: hookgonefail1: the hook was deleted although a handle held it open, so this runner cannot make a delete fail (unknown, not red)"
    } else {
        Check "hookgonefail1 fixture: settings.json is a link, so link mode ran" $hfLinked
        Check "hookgonefail1 fixture: the hook is still there, so its delete failed" ($null -ne $hfText)
        $hfNamed = @($hfLines | Where-Object { $_ -match '(?i)hook.*(fail|could not|cannot|error)' }).Count -ge 1
        Check "hookgonefail1: install.ps1 still writes its run summary line to the install log" ($null -ne $hfMode)
        Check "hookgonefail1: the summary line's hook= field does not state a removal" ($null -ne $hfMode -and $hfMode -ne 'removed')
        Check "hookgonefail1: the install log names the hook and says the delete failed" $hfNamed
        # The delete-failed line is install.ps1's own log line too: it must carry the zone offset.
        $hfOffset = Get-Date -Format zzz
        $hfStamps = @(Get-InstallLogStampProblems @($hfLines) 'install.ps1:' $hfOffset)
        Check "hookgonefail1: each install.ps1 install-log line, the delete-failed line included, carries the zone offset ($hfOffset)" ($hfStamps.Count -eq 0)
        if ($hfStamps.Count) { Write-Host "  hookgonefail1 stamp problems: $($hfStamps -join ' | ')" }
        if (-not $hfNamed -or $null -eq $hfMode) { Write-Host "  hookgonefail1: exit $($hfRes.Exit); log hook= '$hfMode'; install log: $($hfLines -join ' | ')" }
    }
} finally {
    if ($HfHold) { $HfHold.Dispose() }
    Remove-Item -Recurse -Force $HfRoot -ErrorAction SilentlyContinue
}

$HwRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-hookwrite1-" + [guid]::NewGuid().ToString('N'))
$HwHome = Join-Path $HwRoot 'home'
$HwCfg  = Join-Path $HwRoot 'claude'
$HwLogs = Join-Path $HwRoot 'logs'
New-Item -ItemType Directory -Force -Path $HwHome, $HwLogs | Out-Null
try {
    $hwMain = New-PinFixture $HwRoot
    Set-HookFile $hwMain ($HookUtf8.GetBytes("#!/bin/sh`n$HookMarker`n# stale body`nexit 0`n"))
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try { $hwRes = Invoke-InstallProc (Join-Path $hwMain 'install.ps1') $HwCfg $HwHome $HwLogs }
    finally { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
    $hwSet  = Join-Path $HwCfg 'settings.json'
    $hwText = Get-HookFileText $hwMain
    Check "hookwrite1 fixture: settings.json is a copy, so copy mode ran" ((Test-Path -LiteralPath $hwSet) -and -not (Test-ReparsePoint $hwSet))
    Check "hookwrite1: install.ps1 exits 0" ($hwRes.Exit -eq 0)
    Check "hookwrite1: the marked post-merge hook is still there when symlinks fail" ($null -ne $hwText -and $hwText.Contains($HookMarker))
    Check "hookwrite1: the hook was rewritten, not left as the stale one" ($null -ne $hwText -and -not $hwText.Contains('# stale body'))
    Check "hookwrite1: the install log's hook= field says installed" ((Get-InstallLogHookMode $HwCfg) -eq 'installed')
    # install.ps1's own log lines carry the zone offset this host has now.
    $hwOffset = Get-Date -Format zzz
    $hwStamps = @(Get-InstallLogStampProblems @(Get-InstallLogLines $HwCfg) 'install.ps1:' $hwOffset)
    Check "hookwrite1: each install.ps1 install-log line starts with an ISO 8601 stamp that carries the zone offset ($hwOffset)" ($hwStamps.Count -eq 0)
    if ($hwStamps.Count) { Write-Host "  hookwrite1 stamp problems: $($hwStamps -join ' | ')" }
    # The post-merge hook's own log lines: the hook text install.ps1 wrote, read here, not run (see the gap note).
    # No date stamp in it may lack the zone offset, and the offset form must be used.
    $hwBareStamp = ($null -ne $hwText) -and (($hwText -match '\$\(date\)') -or ($hwText -match 'date \+%Y-%m-%dT%H:%M:%S\)'))
    Check "hookwrite1: the post-merge hook writes no date stamp without the zone offset" (($null -ne $hwText) -and -not $hwBareStamp)
    Check "hookwrite1: the post-merge hook formats its stamps with the zone offset" (($null -ne $hwText) -and ($hwText -match '%:?z|-Iseconds'))
    if ($hwRes.Exit -ne 0) { Write-Host "  hookwrite1 output: $($hwRes.Text)" }
} finally {
    Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $HwRoot -ErrorAction SilentlyContinue
}

$LsRoot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-pinlivestale1-" + [guid]::NewGuid().ToString('N'))
$LsHome = Join-Path $LsRoot 'home'
$LsCfg  = Join-Path $LsRoot 'claude'
$LsLogs = Join-Path $LsRoot 'logs'
New-Item -ItemType Directory -Force -Path $LsHome, $LsLogs | Out-Null
try {
    $lsMain = New-PinFixture $LsRoot
    $lsPin  = $lsMain + '-live'
    git -C $lsMain worktree add -q --detach $lsPin | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: pinlivestale1 fixture: git worktree add failed"; $Failed++
    } else {
        Remove-Item -Recurse -Force $lsPin
        $lsListed = @(& git -C $lsMain worktree list --porcelain) -match 'clone-live$'
        if (-not $lsListed) {
            Write-Host "FAIL: pinlivestale1 fixture: git no longer lists the stale pinned checkout"; $Failed++
        } else {
            $lsRes = Invoke-InstallProc (Join-Path $lsMain 'install.ps1') $LsCfg $LsHome $LsLogs
            Check "pinlivestale1: install.ps1 with a deleted but still registered <clone>-live exits non-zero" ($lsRes.Exit -ne 0)
            Check "pinlivestale1: the failure line carries git's message or names the stale registration" ($lsRes.Text -match 'registered|prune')
            if ($lsRes.Exit -eq 0) { Write-Host "  pinlivestale1 output: $($lsRes.Text)" }
        }
    }
} finally {
    Remove-Item -Recurse -Force $LsRoot -ErrorAction SilentlyContinue
}

# ---- linkfallback1: a refused New-Item link falls back to mklink, and the link is made, not a copy ----
# On Windows PowerShell 5.1 without elevation, New-Item -ItemType SymbolicLink throws
# UnauthorizedAccessException (FullyQualifiedErrorId
# NewItemSymbolicLinkElevationRequired), and `cmd /c mklink` makes a SymbolicLink. This case needs
# no admin and no product seam. It loads New-Link from install.ps1 and shadows New-Item in this
# process, so the link call is refused every time, as it is for an account without the symlink
# right. Every other New-Item call still reaches the cmdlet. Install-File copies only when New-Link
# throws, so a link here is the link path. New-Link is the one home for every symlink try.
# Without the mklink fallback, New-Link throws on the refused call, so Install-File would copy. A probe
# skips the case when mklink cannot make a symlink on this account; that is unknown, never red.
$LfTmp  = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-linkfallback-" + [guid]::NewGuid().ToString('N'))
$lfDDst = Join-Path $LfTmp 'dest-dir'
$lfPrevForce = $env:CLAUDE_SETTINGS_FORCE_COPY
New-Item -ItemType Directory -Force -Path $LfTmp | Out-Null
try {
    $lfProbeT = Join-Path $LfTmp 'probe-target.txt'
    $lfProbeL = Join-Path $LfTmp 'probe-link.txt'
    Set-Content -Path $lfProbeT -Value 'p' -Encoding utf8
    cmd /c mklink "$lfProbeL" "$lfProbeT" | Out-Null
    $lfMkExit = $LASTEXITCODE
    $lfProbeI = Get-Item -LiteralPath $lfProbeL -Force -ErrorAction SilentlyContinue
    $lfProbeOk = ($lfMkExit -eq 0) -and [bool]$lfProbeI -and ($lfProbeI.LinkType -eq 'SymbolicLink')

    if (-not $lfProbeOk) {
        Write-Host "SKIP: linkfallback1: mklink cannot make a symlink on this account (needs Developer Mode or elevation)"
    } else {
        # Load every function definition in install.ps1 this file has not defined yet. Definitions
        # only: install.ps1's top-level code does not run, and the quiet Log above stays in place.
        $lfAst = [System.Management.Automation.Language.Parser]::ParseInput($Source, [ref]$null, [ref]$null)
        foreach ($lfFn in $lfAst.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
            if (-not (Test-Path -LiteralPath ('Function:\' + $lfFn.Name))) { Invoke-Expression $lfFn.Extent.Text }
        }

        $lfSrc  = Join-Path $LfTmp 'src-file.txt'
        $lfDest = Join-Path $LfTmp 'dest-file.txt'
        $lfDir  = Join-Path $LfTmp 'src-dir'
        Set-Content -Path $lfSrc -Value 'v1' -Encoding utf8
        New-Item -ItemType Directory -Force -Path $lfDir | Out-Null
        $env:CLAUDE_SETTINGS_FORCE_COPY = $null   # New-Link must reach the New-Item call, not the forced-copy throw

        # Refuse the link call the way the cmdlet does on a non-elevated account (see above).
        function New-Item {
            if ("$args" -match 'SymbolicLink') {
                throw [System.UnauthorizedAccessException]::new('Administrator privilege required for this operation.')
            }
            Microsoft.PowerShell.Management\New-Item @args
        }
        $lfErrF = $null
        $lfErrD = $null
        try { New-Link $lfDest $lfSrc } catch { $lfErrF = $_.Exception.Message }
        try { New-Link $lfDDst $lfDir } catch { $lfErrD = $_.Exception.Message }
        Remove-Item Function:\New-Item

        $lfF = Get-Item -LiteralPath $lfDest -Force -ErrorAction SilentlyContinue
        $lfD = Get-Item -LiteralPath $lfDDst -Force -ErrorAction SilentlyContinue
        Check "linkfallback1: file: New-Link links when New-Item's link call is refused and mklink works" ((-not $lfErrF) -and [bool]$lfF -and ($lfF.LinkType -eq 'SymbolicLink'))
        Check "linkfallback1: file: the link targets the source file" ([bool]$lfF -and (([string]($lfF.Target | Select-Object -First 1)) -eq $lfSrc))
        Check "linkfallback1: directory: New-Link links the directory, not a copy (mklink /D)" ((-not $lfErrD) -and [bool]$lfD -and ($lfD.LinkType -eq 'SymbolicLink') -and $lfD.PSIsContainer)
        if ($lfErrF) { Write-Host "  linkfallback1 file error: $lfErrF" }
        if ($lfErrD) { Write-Host "  linkfallback1 directory error: $lfErrD" }
    }
} finally {
    if (Test-Path 'Function:\New-Item') { Remove-Item Function:\New-Item }
    $env:CLAUDE_SETTINGS_FORCE_COPY = $lfPrevForce
    # A directory link goes by IO.Directory.Delete: a recursive delete can enter a link's target.
    $lfDi = Get-Item -LiteralPath $lfDDst -Force -ErrorAction SilentlyContinue
    if ($lfDi -and $lfDi.LinkType) { [IO.Directory]::Delete($lfDDst) }
    Remove-Item -Recurse -Force $LfTmp -ErrorAction SilentlyContinue
}
} else {
    Write-Host "SKIP: copymode1: install.ps1 runs only on Windows"
    Write-Host "SKIP: settingsrepeat1: install.ps1 runs only on Windows"
    Write-Host "SKIP: firstinstall1: install.ps1 runs only on Windows"
    Write-Host "SKIP: envkey1: install.ps1 runs only on Windows"
    Write-Host "SKIP: refusewt1: install.ps1 runs only on Windows"
    Write-Host "SKIP: keepwt1: install.ps1 runs only on Windows"
    Write-Host "SKIP: pinnedps1: install.ps1 runs only on Windows"
    Write-Host "SKIP: pinnedwt1: install.ps1 runs only on Windows"
    Write-Host "SKIP: pinlivewt1: install.ps1 runs only on Windows"
    Write-Host "SKIP: pinlivewt2: install.ps1 runs only on Windows"
    Write-Host "SKIP: pinlivehook1: install.ps1 runs only on Windows"
    Write-Host "SKIP: hookgone1: install.ps1 runs only on Windows"
    Write-Host "SKIP: hookkeep1: install.ps1 runs only on Windows"
    Write-Host "SKIP: hookkeepagents1: install.ps1 runs only on Windows"
    Write-Host "SKIP: hookgonefail1: install.ps1 runs only on Windows"
    Write-Host "SKIP: hookwrite1: install.ps1 runs only on Windows"
    Write-Host "SKIP: pinlivestale1: install.ps1 runs only on Windows"
    Write-Host "SKIP: linkfallback1: install.ps1 runs only on Windows"
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

# ---- retired files: ps1 twins of hooks/test_install_src.sh retired2, 3, 4, 5, 6 -----------------
# Copy mode (CLAUDE_SETTINGS_FORCE_COPY=1) lands every file as a copy, the mode the incident hit.
# Shipped = git lists the file under the clone (tracked, or untracked and not ignored). The manifest is $CLAUDE_DIR\backups\install-manifest.txt.
# Red on the current install.ps1 is unmeasured locally: no pwsh runs in the authoring session.
# The cases use a fresh clone each, built here: New-WtFixture makes a worktree pair, not one clone.
function New-RetiredClone([string]$Root) {
    $clone = Join-Path $Root 'clone'
    New-Item -ItemType Directory -Force -Path (Join-Path $clone 'hooks'), (Join-Path $clone 'skills\keep-skill') | Out-Null
    Copy-Item (Join-Path $Here 'install.ps1') (Join-Path $clone 'install.ps1')
    Set-Content -Path (Join-Path $clone 'CLAUDE.md') -Value '# retired content' -Encoding utf8
    Set-Content -Path (Join-Path $clone 'settings.json') -Value '{}' -Encoding utf8
    Set-Content -Path (Join-Path $clone 'landed-dirs.txt') -Value "hooks`nskills" -Encoding utf8
    Set-Content -Path (Join-Path $clone 'hooks\keep_hook.py') -Value 'keep' -Encoding utf8
    Set-Content -Path (Join-Path $clone 'skills\keep-skill\SKILL.md') -Value 'keep' -Encoding utf8
    git -C $clone init -q -b main | Out-Null
    git -C $clone add -A | Out-Null
    git -C $clone -c user.email=t@example.com -c user.name=t commit -q -m base | Out-Null
    return $clone
}

# Commit everything the clone holds now. Call it only when no ignored-only leftover is on disk yet.
function Save-RetiredClone([string]$Clone, [string]$Msg) {
    git -C $Clone add -A | Out-Null
    git -C $Clone -c user.email=t@example.com -c user.name=t commit -q -m $Msg | Out-Null
}

# retiredps1-a (retired2): a copy of a hook and a skill main stopped tracking is removed on the next run.
$RtAroot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-retired-a-" + [guid]::NewGuid().ToString('N'))
$RtAhome = Join-Path $RtAroot 'home'; $RtAcfg = Join-Path $RtAroot 'claude'; $RtAlogs = Join-Path $RtAroot 'logs'
New-Item -ItemType Directory -Force -Path $RtAhome, $RtAcfg, $RtAlogs | Out-Null
try {
    $rtAclone = New-RetiredClone $RtAroot
    Set-Content -Path (Join-Path $rtAclone 'hooks\retired_copy.py') -Value 'copy' -Encoding utf8
    New-Item -ItemType Directory -Force -Path (Join-Path $rtAclone 'skills\retired-skill') | Out-Null
    Set-Content -Path (Join-Path $rtAclone 'skills\retired-skill\SKILL.md') -Value 'old skill' -Encoding utf8
    Save-RetiredClone $rtAclone 'ship retired copies'
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rtA1 = Invoke-InstallProc (Join-Path $rtAclone 'install.ps1') $RtAcfg $RtAhome $RtAlogs
        git -C $rtAclone rm -q hooks/retired_copy.py | Out-Null
        git -C $rtAclone rm -q -r skills/retired-skill | Out-Null
        Save-RetiredClone $rtAclone 'retire the copies'
        $rtA2 = Invoke-InstallProc (Join-Path $rtAclone 'install.ps1') $RtAcfg $RtAhome $RtAlogs
    } finally { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
    Check "retiredps1-a: both runs exit 0" ($rtA1.Exit -eq 0 -and $rtA2.Exit -eq 0)
    Check "retiredps1-a: the retired hook copy is removed by the second run" (-not (Test-Path -LiteralPath (Join-Path $RtAcfg 'hooks\retired_copy.py')))
    Check "retiredps1-a: the retired skill copy is removed by the second run" (-not (Test-Path -LiteralPath (Join-Path $RtAcfg 'skills\retired-skill')))
} finally {
    Remove-Item -Recurse -Force $RtAroot -ErrorAction SilentlyContinue
}

# retiredps1-b (retired3): an owner's file the manifest does not list is kept. Passes on the current installer.
$RtBroot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-retired-b-" + [guid]::NewGuid().ToString('N'))
$RtBhome = Join-Path $RtBroot 'home'; $RtBcfg = Join-Path $RtBroot 'claude'; $RtBlogs = Join-Path $RtBroot 'logs'
New-Item -ItemType Directory -Force -Path $RtBhome, $RtBcfg, $RtBlogs | Out-Null
try {
    $rtBclone = New-RetiredClone $RtBroot
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rtB1 = Invoke-InstallProc (Join-Path $rtBclone 'install.ps1') $RtBcfg $RtBhome $RtBlogs
        Set-Content -Path (Join-Path $RtBcfg 'hooks\owner_tool.py') -Value 'mine' -Encoding utf8
        $rtB2 = Invoke-InstallProc (Join-Path $rtBclone 'install.ps1') $RtBcfg $RtBhome $RtBlogs
    } finally { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
    $rtBgot = if (Test-Path -LiteralPath (Join-Path $RtBcfg 'hooks\owner_tool.py')) { (Get-Content -Raw -LiteralPath (Join-Path $RtBcfg 'hooks\owner_tool.py')).Trim() } else { $null }
    Check "retiredps1-b: both runs exit 0" ($rtB1.Exit -eq 0 -and $rtB2.Exit -eq 0)
    Check "retiredps1-b: an owner's file the manifest does not list keeps its content" ($rtBgot -eq 'mine')
} finally {
    Remove-Item -Recurse -Force $RtBroot -ErrorAction SilentlyContinue
}

# retiredps1-c (retired4): a recorded copy the owner hand-edited is kept, and the next run names it.
$RtCroot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-retired-c-" + [guid]::NewGuid().ToString('N'))
$RtChome = Join-Path $RtCroot 'home'; $RtCcfg = Join-Path $RtCroot 'claude'; $RtClogs = Join-Path $RtCroot 'logs'
New-Item -ItemType Directory -Force -Path $RtChome, $RtCcfg, $RtClogs | Out-Null
try {
    $rtCclone = New-RetiredClone $RtCroot
    Set-Content -Path (Join-Path $rtCclone 'hooks\edited_hook.py') -Value 'print("v1")' -Encoding utf8
    Save-RetiredClone $rtCclone 'ship edited_hook'
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rtC1 = Invoke-InstallProc (Join-Path $rtCclone 'install.ps1') $RtCcfg $RtChome $RtClogs
        Set-Content -Path (Join-Path $RtCcfg 'hooks\edited_hook.py') -Value 'print("mine")' -Encoding utf8
        git -C $rtCclone rm -q hooks/edited_hook.py | Out-Null
        Save-RetiredClone $rtCclone 'retire edited_hook'
        $rtC2 = Invoke-InstallProc (Join-Path $rtCclone 'install.ps1') $RtCcfg $RtChome $RtClogs
    } finally { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
    $rtCgot = if (Test-Path -LiteralPath (Join-Path $RtCcfg 'hooks\edited_hook.py')) { (Get-Content -Raw -LiteralPath (Join-Path $RtCcfg 'hooks\edited_hook.py')).Trim() } else { $null }
    Check "retiredps1-c: both runs exit 0" ($rtC1.Exit -eq 0 -and $rtC2.Exit -eq 0)
    Check "retiredps1-c: the hand-edited copy keeps the owner's edit" ($rtCgot -eq 'print("mine")')
    Check "retiredps1-c: the second run names edited_hook.py in its output" ($rtC2.Text -match 'edited_hook\.py')
} finally {
    Remove-Item -Recurse -Force $RtCroot -ErrorAction SilentlyContinue
}

# retiredps1-d (retired5): with no manifest, an owner's real folder under a listed skill name is moved to backups\retired.
$RtDroot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-retired-d-" + [guid]::NewGuid().ToString('N'))
$RtDhome = Join-Path $RtDroot 'home'; $RtDcfg = Join-Path $RtDroot 'claude'; $RtDlogs = Join-Path $RtDroot 'logs'
New-Item -ItemType Directory -Force -Path $RtDhome, $RtDcfg, $RtDlogs | Out-Null
try {
    $rtDclone = New-RetiredClone $RtDroot
    Set-Content -Path (Join-Path $rtDclone 'retired-files.txt') -Value 'skills/tile-windows' -Encoding utf8
    Save-RetiredClone $rtDclone 'retired list'
    New-Item -ItemType Directory -Force -Path (Join-Path $RtDcfg 'skills\tile-windows') | Out-Null
    Set-Content -Path (Join-Path $RtDcfg 'skills\tile-windows\SKILL.md') -Value 'owner skill text' -Encoding utf8
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rtD1 = Invoke-InstallProc (Join-Path $rtDclone 'install.ps1') $RtDcfg $RtDhome $RtDlogs
    } finally { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
    $rtDkept = @(Get-ChildItem -LiteralPath (Join-Path $RtDcfg 'backups\retired') -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { (Get-Content -Raw -LiteralPath $_.FullName) -match 'owner skill text' })
    Check "retiredps1-d: the run exits 0" ($rtD1.Exit -eq 0)
    Check "retiredps1-d: the owner's folder is gone from skills\" (-not (Test-Path -LiteralPath (Join-Path $RtDcfg 'skills\tile-windows')))
    Check "retiredps1-d: the owner's SKILL.md is under backups\retired" ($rtDkept.Count -ge 1)
} finally {
    Remove-Item -Recurse -Force $RtDroot -ErrorAction SilentlyContinue
}

# retiredps1-e (retired6): a folder holding only an ignored file is not landed, and an old copy of it is removed.
$RtEroot = Join-Path ([IO.Path]::GetTempPath()) ("claude-settings-retired-e-" + [guid]::NewGuid().ToString('N'))
$RtEhome = Join-Path $RtEroot 'home'; $RtEcfg = Join-Path $RtEroot 'claude'; $RtElogs = Join-Path $RtEroot 'logs'
New-Item -ItemType Directory -Force -Path $RtEhome, $RtEcfg, $RtElogs | Out-Null
try {
    $rtEclone = New-RetiredClone $RtEroot
    Set-Content -Path (Join-Path $rtEclone '.gitignore') -Value '*.local' -Encoding utf8
    New-Item -ItemType Directory -Force -Path (Join-Path $rtEclone 'skills\tile-windows') | Out-Null
    Set-Content -Path (Join-Path $rtEclone 'skills\tile-windows\SKILL.md') -Value 'tile' -Encoding utf8
    Save-RetiredClone $rtEclone 'ship tile-windows'
    $env:CLAUDE_SETTINGS_FORCE_COPY = '1'
    try {
        $rtE1 = Invoke-InstallProc (Join-Path $rtEclone 'install.ps1') $RtEcfg $RtEhome $RtElogs
        # main drops tile-windows. The folder keeps only an ignored file; ghost-skill was never tracked.
        git -C $rtEclone rm -q -r skills/tile-windows | Out-Null
        Save-RetiredClone $rtEclone 'retire tile-windows'
        New-Item -ItemType Directory -Force -Path (Join-Path $rtEclone 'skills\tile-windows'), (Join-Path $rtEclone 'skills\ghost-skill') | Out-Null
        Set-Content -Path (Join-Path $rtEclone 'skills\tile-windows\cache.local') -Value 'cache' -Encoding utf8
        Set-Content -Path (Join-Path $rtEclone 'skills\ghost-skill\cache.local') -Value 'cache' -Encoding utf8
        $rtE2 = Invoke-InstallProc (Join-Path $rtEclone 'install.ps1') $RtEcfg $RtEhome $RtElogs
    } finally { Remove-Item Env:\CLAUDE_SETTINGS_FORCE_COPY -ErrorAction SilentlyContinue }
    Check "retiredps1-e: both runs exit 0" ($rtE1.Exit -eq 0 -and $rtE2.Exit -eq 0)
    Check "retiredps1-e: the old copy of tile-windows is removed" (-not (Test-Path -LiteralPath (Join-Path $RtEcfg 'skills\tile-windows')))
    Check "retiredps1-e: ghost-skill, never tracked, is not landed" (-not (Test-Path -LiteralPath (Join-Path $RtEcfg 'skills\ghost-skill')))
} finally {
    Remove-Item -Recurse -Force $RtEroot -ErrorAction SilentlyContinue
}

if ($Failed) { Write-Host "$Failed case(s) failed"; exit 1 }
Write-Host "all cases passed"
exit 0
