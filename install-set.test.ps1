# Tests for the install set. An install swaps every guard module at once. One install runs at a
# time. Each installer path logs one start and one end line.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-set.test.ps1
#
# Windows only; elsewhere it prints SKIP and exits 0. Exits 1 on any FAIL. Copy mode only
# (CLAUDE_SETTINGS_FORCE_COPY=1), so the installed guard files are stamped copies. Link mode is not
# covered: a link carries the repo file's placeholder line, so an install cannot make the guard see
# an INSTALL_ID mix there.
#
# Cases. Each FAIL line names the bad outcome.
#   swap1   A sibling guard file is held open with read sharing only, so the installer's rename
#           over it is refused, as a reader holding it would refuse it. A second install then stalls
#           mid-swap. No guard run made while that install is alive may be a guard-crash deny. After
#           the install, the guard loads the second install's id.
#   lock1   The second install starts only after the first has logged its start line, which it does
#           once it holds the lock, so the first is still alive when the second starts. The second's
#           start line must come after the first's end line: the second waits, or it exits with one
#           clear line about the lock. Two pairs: install.ps1 against install.ps1, and install.ps1
#           against the git post-merge hook.
#   lock2   install.ps1 given CLAUDE_SETTINGS_LOCK_TOKEN equal to line 1 of the lock file runs without
#           waiting, logs its own start and end, and leaves the lock. Any other token waits, then exits
#           1 with one lock line and writes nothing.
#   log3    install.ps1 and the post-merge hook each log one start line and one end line, naming
#           the install id and the process id. install.sh does not run on Windows, so it has no leg here.
#
# Every case works under its own folder in a temp root. None touches the real ~/.claude. The
# sampling loops are bounded by a deadline and read local files only; they measure, they do not wait
# on anything outside this machine.
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { Write-Host 'SKIP: install set (Windows only)'; exit 0 }

$Here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Utf8    = New-Object Text.UTF8Encoding($false)
. (Join-Path $Here 'testing\TrackedTree.ps1')  # copies what git lists, so no fixture lists files
$PsHost  = (Get-Process -Id $PID).Path
$Python  = (Get-Command python -ErrorAction Stop).Source
$GitExe  = (Get-Command git -ErrorAction Stop).Source
$BashExe = Join-Path (Split-Path -Parent (Split-Path -Parent $GitExe)) 'bin\bash.exe'
if (-not (Test-Path -LiteralPath $BashExe)) { Write-Host "FAIL: setup: no Git Bash at $BashExe"; exit 1 }

$Failed = 0
function Check([string]$name, [bool]$ok, [string]$why) {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: ${name}: $why"; $script:Failed++ }
}

$Root   = Join-Path ([IO.Path]::GetTempPath()) ('install-set-' + [guid]::NewGuid().ToString('N'))
$NoGit  = Join-Path $Root 'nogit'
$EnvSub = 'Software\install-set-test-' + [guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Force -Path $NoGit | Out-Null
[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($EnvSub).Close()

# Prints the INSTALL_ID values the guard loads: the entry guard.py and every guard_* module it imports.
# It imports the installed guard the way the hook does, so it reads the set the guard really loads.
$ProbePy = Join-Path $Root 'loaded-ids.py'
$ProbeText = @'
import runpy, sys
ns = runpy.run_path(sys.argv[1], run_name="guard_probe")
ids = {str(getattr(m, "INSTALL_ID", "(none)")) for name, m in list(sys.modules.items()) if name.startswith("guard")}
ids.add(str(ns.get("INSTALL_ID", "(none)")))
print("\n".join(sorted(ids)))
'@
[IO.File]::WriteAllText($ProbePy, ($ProbeText -replace "`r", ''), $Utf8)

# Reads a file with read, write and delete sharing, so an installer rename is never refused by a
# sampler. A missing or unreadable file throws; the callers catch it.
function Read-Shared([string]$Path) {
    $share = [IO.FileShare]([int][IO.FileShare]::ReadWrite -bor [int][IO.FileShare]::Delete)
    $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
    try { $sr = New-Object IO.StreamReader($fs, $Utf8); return $sr.ReadToEnd() } finally { $fs.Close() }
}

# Holds a file open for read with no delete sharing. A rename over the file is refused while it is held.
function Hold-File([string]$Path) {
    return [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
}

# The one INSTALL_ID the guard loads from a config dir, or '' when none, or the loaded modules disagree,
# or the import fails. The import runs the guard's own loader, so a mixed set shows up here too.
function Get-LoadedId([string]$Cfg) {
    $o = Join-Path $Root ('probe-' + [guid]::NewGuid().ToString('N'))
    $saved = @{}
    foreach ($n in @('CLAUDE_CONFIG_DIR', 'PYTHONPATH')) { $saved[$n] = [Environment]::GetEnvironmentVariable($n) }
    [Environment]::SetEnvironmentVariable('CLAUDE_CONFIG_DIR', $Cfg)
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $null)
    try {
        $p = Start-Process -FilePath $Python -Wait -PassThru -NoNewWindow -WorkingDirectory $NoGit `
            -ArgumentList @(('"' + $ProbePy + '"'), ('"' + (Join-Path $Cfg 'hooks\guard.py') + '"')) `
            -RedirectStandardOutput "$o.out" -RedirectStandardError "$o.err"
    } finally { foreach ($n in $saved.Keys) { [Environment]::SetEnvironmentVariable($n, $saved[$n]) } }
    if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath "$o.out")) { return '' }
    $ids = @([IO.File]::ReadAllText("$o.out") -split '\r?\n' | Where-Object { $_ -ne '' } | Select-Object -Unique)
    if ($ids.Count -eq 1 -and $ids[0] -notlike '(*') { return $ids[0] }
    return ''
}

# Saves the named environment variables, sets them, and returns the saved values for Restore-Env.
function Set-Env([hashtable]$Values) {
    $saved = @{}
    foreach ($n in $Values.Keys) {
        $saved[$n] = [Environment]::GetEnvironmentVariable($n)
        [Environment]::SetEnvironmentVariable($n, $Values[$n])
    }
    return $saved
}
function Restore-Env([hashtable]$Saved) {
    foreach ($n in $Saved.Keys) { [Environment]::SetEnvironmentVariable($n, $Saved[$n]) }
}

# Appends a build line to each guard file in a clone's hooks folder, in place. Nothing is committed.
function Add-BuildLine([string]$Dir, [string]$Build) {
    foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $Dir 'hooks') -File | Where-Object { $_.Name -ceq 'guard.py' -or $_.Name -clike 'guard_*.py' })) {
        $text = [IO.File]::ReadAllText($f.FullName)
        [IO.File]::WriteAllText($f.FullName, $text + "`n# build $Build`n", $Utf8)
    }
}

# A clone folder: install.ps1, the repo's hook modules (testing\TrackedTree.ps1) with a build line appended to each guard file,
# and a settings.json and CLAUDE.md. With -Skills N it also lands N skill folders after the hooks, so
# an install runs long enough to overlap another. With -Git it is a git repository on main.
function New-Clone([string]$Dir, [string]$Build, [int]$Skills = 0, [switch]$Git) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Dir 'hooks') | Out-Null
    Copy-Item -LiteralPath (Join-Path $Here 'install.ps1') -Destination (Join-Path $Dir 'install.ps1')
    [IO.File]::WriteAllText((Join-Path $Dir 'CLAUDE.md'), "# fixture $Build`n", $Utf8)
    [IO.File]::WriteAllText((Join-Path $Dir 'settings.json'), "{}`n", $Utf8)
    $lands = if ($Skills -gt 0) { "hooks`nskills`n" } else { "hooks`n" }
    [IO.File]::WriteAllText((Join-Path $Dir 'landed-dirs.txt'), $lands, $Utf8)
    Copy-TrackedFolder $Here 'hooks' (Join-Path $Dir 'hooks') | Out-Null  # every module the guard may import
    Add-BuildLine $Dir $Build
    for ($i = 0; $i -lt $Skills; $i++) {
        $d = Join-Path $Dir ('skills\skill-' + $i)
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        for ($k = 0; $k -lt 6; $k++) { [IO.File]::WriteAllText((Join-Path $d ("f$k.md")), "skill $i file $k`n", $Utf8) }
    }
    if ($Git) {
        & $GitExe -C $Dir init -q -b main | Out-Null
        & $GitExe -C $Dir add -A | Out-Null
        & $GitExe -C $Dir -c user.name=test -c user.email=test@example.invalid commit -q -m "fixture $Build" | Out-Null
    }
}

# Starts install.ps1 from a clone, copy mode, into $Cfg. Stdout and stderr go to $Out.out.txt and $Out.err.txt.
# $Extra sets more environment for this run only. The lock token and wait are cleared first, so no case
# inherits them from the shell that runs the test.
function Start-Install([string]$Clone, [string]$Cfg, [string]$Out, [hashtable]$Extra = @{}) {
    $vals = @{
        CLAUDE_CONFIG_DIR = $Cfg; CLAUDE_SETTINGS_FORCE_COPY = '1'
        CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$EnvSub"; USERPROFILE = $NoGit
        CLAUDE_SETTINGS_LOCK_TOKEN = $null; CLAUDE_SETTINGS_LOCK_WAIT = $null }
    foreach ($k in $Extra.Keys) { $vals[$k] = $Extra[$k] }
    $saved = Set-Env $vals
    try {
        $proc = Start-Process -FilePath $PsHost -PassThru -NoNewWindow -WorkingDirectory $NoGit `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $Clone 'install.ps1') + '"')) `
            -RedirectStandardOutput "$Out.out.txt" -RedirectStandardError "$Out.err.txt"
        $null = $proc.Handle   # cache the handle now: without it, ExitCode reads back empty after exit
        return $proc
    } finally { Restore-Env $saved }
}

# Writes a bash script that runs one post-merge hook from a clone, and prints the pid
# of that child as bash sees it ($!). The child's own $$ is the same number.
function Write-ShellRun([string]$Path, [string]$GitDir, [string]$Cfg, [string]$Command, [string]$Label) {
    $g = $GitDir -replace '\\', '/'
    $c = $Cfg -replace '\\', '/'
    # The shell run keeps HOME in a scratch folder, so nothing it starts can write to the real home.
    $h = (Join-Path $Root 'shhome') -replace '\\', '/'
    New-Item -ItemType Directory -Force -Path ($h -replace '/', '\') | Out-Null
    $lines = @('#!/bin/sh', "cd `"$g`" || exit 9", "export HOME=`"$h`"", "export SHELL=/bin/bash", "export CLAUDE_CONFIG_DIR=`"$c`"",
               "$Command &", "p=`$!", "echo `"${Label}PID=`$p`"", "wait `$p", "echo `"${Label}EXIT=`$?`"")
    [IO.File]::WriteAllText($Path, (($lines -join "`n") + "`n"), $Utf8)
}

# Starts a bash script with Git Bash (not the WSL stub that a bare `bash` can resolve to).
function Start-Shell([string]$Script, [string]$Out) {
    $proc = Start-Process -FilePath $BashExe -PassThru -NoNewWindow -WorkingDirectory $NoGit -ArgumentList @(($Script -replace '\\', '/')) `
        -RedirectStandardOutput "$Out.out.txt" -RedirectStandardError "$Out.err.txt"
    $null = $proc.Handle   # cache the handle now, as Start-Install does
    return $proc
}

# One guard run through the installed hook entry, the way Claude Code runs it: the payload on stdin.
# The payload is a plain `ls`, which the guard allows when it loads.
$GuardPayload = ConvertTo-Json -Compress @{ tool_name = 'Bash'; tool_input = @{ command = 'ls' }; cwd = $NoGit }
function Invoke-Guard([string]$Cfg, [string]$Tag) {
    $in = Join-Path $Root "guard-$Tag.in"
    [IO.File]::WriteAllText($in, $GuardPayload, $Utf8)
    $saved = Set-Env @{ CLAUDE_CONFIG_DIR = $Cfg; CLAUDE_GUARD_ROOT_PID = "$PID"; CLAUDE_CODE_SESSION_ID = $null; PYTHONPATH = $null }
    try {
        $p = Start-Process -FilePath $Python -Wait -PassThru -NoNewWindow -WorkingDirectory $NoGit `
            -ArgumentList @(('"' + (Join-Path $Cfg 'hooks\guard.py') + '"')) `
            -RedirectStandardInput $in -RedirectStandardOutput "$in.out" -RedirectStandardError "$in.err"
    } finally { Restore-Env $saved }
    $text = if (Test-Path -LiteralPath "$in.out") { [IO.File]::ReadAllText("$in.out").Trim() } else { '' }
    return @{ Exit = $p.ExitCode; Text = $text }
}

# The decision of one guard run. Empty stdout is an allow.
function Get-Decision([string]$Text) {
    if (-not $Text) { return @{ Decision = 'allow'; Reason = '' } }
    try {
        $block = (ConvertFrom-Json $Text).hookSpecificOutput
        return @{ Decision = $block.permissionDecision; Reason = [string]$block.permissionDecisionReason }
    } catch { return @{ Decision = 'unparsable'; Reason = $Text } }
}

# Log lines that carry the word, the id and the process id. A pid must stand alone, so 42 never matches 142.
function Find-LogLines([string[]]$Lines, [string]$Word, [string]$Id, [int]$ProcId) {
    if (-not $Id) { return @() }
    return @($Lines | Where-Object { $_ -match "(?i)\b$Word\b" -and $_.Contains($Id) -and $_ -match "(?<!\d)$ProcId(?!\d)" })
}

# Log lines that carry the word and "pid=<n>" for one process, found without an id. Every installer path
# writes pid=<n>, and the match needs the "pid=" prefix, so a date's digits never stand in for a pid.
function Find-PidLines([string[]]$Lines, [string]$Word, [int]$ProcId) {
    return @($Lines | Where-Object { $_ -match "(?i)\b$Word\b" -and $_ -match "\bpid=$ProcId(?!\d)" })
}
# Index of the first such line at or after $From, or -1.
function Find-PidLine([string[]]$Lines, [string]$Word, [int]$ProcId, [int]$From = 0) {
    for ($i = $From; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match "(?i)\b$Word\b" -and $Lines[$i] -match "\bpid=$ProcId(?!\d)") { return $i }
    }
    return -1
}

# Line 1 of a lock file, trimmed. A missing or unreadable file gives ''.
function Get-LockLine([string]$Path) {
    try { return ((Read-Shared $Path) -split '\r?\n')[0].Trim() } catch { return '' }
}

# The install log in a config dir, as lines. Missing means no lines.
function Get-InstallLog([string]$Cfg) {
    $path = Join-Path $Cfg 'claude-settings-install.log'
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    try { return @((Read-Shared $path) -split '\r?\n' | Where-Object { $_ -ne '' }) } catch { return @() }
}

# Waits for a process, bounded. Wait-Process throws on a timeout; the caller then reads the exit code it has.
function Wait-Bounded($Process, [int]$Seconds) {
    try { Wait-Process -Id $Process.Id -Timeout $Seconds } catch { }
}

# The text of a run's stdout and stderr files.
function Get-RunText([string]$Out) {
    $parts = @()
    foreach ($f in @("$Out.out.txt", "$Out.err.txt")) { if (Test-Path -LiteralPath $f) { $parts += [IO.File]::ReadAllText($f) } }
    return ($parts -join "`n")
}

# ---- setup: one clean install, so the guard files exist ----------------------------------------
$C0   = Join-Path $Root 'base'
$Cfg0 = Join-Path $C0 'claude'
New-Clone (Join-Path $C0 'src') 'base'
$p0 = Start-Install (Join-Path $C0 'src') $Cfg0 (Join-Path $C0 'run')
Wait-Bounded $p0 180
$baseId = Get-LoadedId $Cfg0
Check 'setup: a plain install leaves one INSTALL_ID loaded by the guard' ($baseId -ne '') "install exit $($p0.ExitCode); the guard loads no single id"

# ---- swap1: a stalled install never makes the installed guard crash -----------------------------
$C1   = Join-Path $Root 'swap1'
$Cfg1 = Join-Path $C1 'claude'
New-Clone (Join-Path $C1 'one') 'one'
New-Clone (Join-Path $C1 'two') 'two' -Skills 40
$p1 = Start-Install (Join-Path $C1 'one') $Cfg1 (Join-Path $C1 'run1')
Wait-Bounded $p1 180
$id1 = Get-LoadedId $Cfg1

$hold1 = Hold-File (Join-Path $Cfg1 'hooks\guard_core.py')
$t1 = Get-Date
$p2 = Start-Install (Join-Path $C1 'two') $Cfg1 (Join-Path $C1 'run2')
$released1 = $false; $loads1 = 0; $crashes1 = 0; $others1 = @()
$deadline1 = (Get-Date).AddSeconds(150)
while (-not $p2.HasExited -and (Get-Date) -lt $deadline1) {
    if (-not $released1 -and ((Get-Date) - $t1).TotalSeconds -ge 9) { $hold1.Close(); $released1 = $true }
    $d = Get-Decision (Invoke-Guard $Cfg1 'swap1').Text
    $loads1++
    if ($d.Decision -eq 'deny' -and $d.Reason -match 'guard-crash') { $crashes1++ }
    elseif ($d.Decision -ne 'allow') { $others1 += "$($d.Decision): $($d.Reason)" }
}
if (-not $released1) { $hold1.Close() }
$elapsed1 = [int]((Get-Date) - $t1).TotalSeconds
Wait-Bounded $p2 150
$id2 = Get-LoadedId $Cfg1

Check 'swap1: precondition, at least 3 guard runs happened while install 2 was alive' ($loads1 -ge 3) "only $loads1 guard runs; the case proves nothing"
Check 'swap1: install 2 exits 0' ($p2.ExitCode -eq 0) "install 2 exit code '$($p2.ExitCode)', HasExited $($p2.HasExited), after $elapsed1 s of guard runs"
Check 'swap1: no guard run during install 2 was a guard-crash deny' ($crashes1 -eq 0) "$crashes1 of $loads1 guard runs were guard-crash denies, while install 2 held a sibling file"
Check 'swap1: no guard run during install 2 was any other deny' ($others1.Count -eq 0) ($others1 | Select-Object -First 1)
Check 'swap1: after install 2 the guard loads install 2 id, one whole set' ($id2 -ne '' -and $id2 -ne $id1) "loaded id after install 2: '$id2' (after install 1: '$id1')"

# ---- lock1: a second install waits for the first, or refuses with one clear line ----------------
# Overlap is forced: the first install holds a sibling file, and it runs a skills tree after the hooks.
# The second starts only once the first's start line names the first's pid. The first writes that line
# after it takes the lock, so from there the second meets the lock, not a race for it. The result is the
# log line index of each run's start and end lines; the checks read the order from those.
function Invoke-Overlap([string]$Cfg, [scriptblock]$StartA, [scriptblock]$StartB, [string]$OutB) {
    $hold = Hold-File (Join-Path $Cfg 'hooks\guard_core.py')
    $tA = Get-Date
    $pA = & $StartA
    $deadlineA = (Get-Date).AddSeconds(60)
    while (-not $pA.HasExited -and (Get-Date) -lt $deadlineA -and
           (Find-PidLine @(Get-InstallLog $Cfg) 'start' $pA.Id) -lt 0) { Start-Sleep -Milliseconds 50 }
    $aStartedAtB = (Find-PidLine @(Get-InstallLog $Cfg) 'start' $pA.Id) -ge 0
    $aAliveAtB = -not $pA.HasExited
    $pB = & $StartB
    $released = $false
    $deadline = (Get-Date).AddSeconds(150)
    while ((-not $pA.HasExited -or -not $pB.HasExited) -and (Get-Date) -lt $deadline) {
        if (-not $released -and ((Get-Date) - $tA).TotalSeconds -ge 9) { $hold.Close(); $released = $true }
        Start-Sleep -Milliseconds 50
    }
    if (-not $released) { $hold.Close() }
    Wait-Bounded $pA 60
    Wait-Bounded $pB 60
    # A shell run (the hook) prints its own pid as HOOKPID; a process run's pid is $pB.Id.
    $bPid = $pB.Id
    $hp = [regex]::Match((Get-RunText $OutB), 'HOOKPID=(\d+)')
    if ($hp.Success) { $bPid = [int]$hp.Groups[1].Value }
    $lines = @(Get-InstallLog $Cfg)
    $aStart = Find-PidLine $lines 'start' $pA.Id
    $aEnd = if ($aStart -ge 0) { Find-PidLine $lines 'end' $pA.Id ($aStart + 1) } else { -1 }
    $bStart = Find-PidLine $lines 'start' $bPid
    $bLockLines = @((Get-RunText $OutB) -split '\r?\n' | Where-Object { $_ -match '(?i)lock|another install|already running|waiting' })
    return @{ AStartedAtB = $aStartedAtB; AAlive = $aAliveAtB; AEnd = $aEnd; BStart = $bStart; BLockLines = $bLockLines.Count }
}

# The lock1 checks for one pair. When B ran, its start line must come after A's end line. When B did not
# run, it must have printed one clear lock line.
function Test-LockOrder([string]$Pair, $R) {
    Check "lock1: install A logged its start and end lines, and was alive when install B started ($Pair)" `
        ($R.AStartedAtB -and $R.AAlive -and $R.AEnd -ge 0) "A's start seen before B: $($R.AStartedAtB); A alive: $($R.AAlive); A's end line: $($R.AEnd)"
    if ($R.BStart -ge 0) {
        Check "lock1: install B's start line came after install A's end line ($Pair)" `
            ($R.BStart -gt $R.AEnd) "B's start is at log line $($R.BStart), A's end at line $($R.AEnd): B started while A held the lock"
    } else {
        Check "lock1: install B never started and printed one clear lock line ($Pair)" `
            ($R.BLockLines -eq 1) "B wrote no start line and printed $($R.BLockLines) lock line(s)"
    }
}

$C2   = Join-Path $Root 'lock1'
$Cfg2 = Join-Path $C2 'claude'
New-Clone (Join-Path $C2 'base') 'base'
New-Clone (Join-Path $C2 'a') 'A' -Skills 60
New-Clone (Join-Path $C2 'b') 'B' -Skills 60
$pBase2 = Start-Install (Join-Path $C2 'base') $Cfg2 (Join-Path $C2 'base-run')
Wait-Bounded $pBase2 180

# Pair 1: install.ps1 against install.ps1.
$r2 = Invoke-Overlap $Cfg2 `
    { Start-Install (Join-Path $C2 'a') $Cfg2 (Join-Path $C2 'a-run') } `
    { Start-Install (Join-Path $C2 'b') $Cfg2 (Join-Path $C2 'b-run') } `
    (Join-Path $C2 'b-run')
Test-LockOrder 'install.ps1 pair' $r2

# Pair 2: install.ps1 against the git post-merge hook (cross-path). The hook is the one install.ps1
# wrote into the git clone, and it copies that clone's working tree. The clone is built base3 for the
# setup install, then its working tree is marked build B (uncommitted), so the setup install holds no B.
$C3   = Join-Path $Root 'lock1-hook'
$Cfg3 = Join-Path $C3 'claude'
New-Clone (Join-Path $C3 'a') 'A' -Skills 60
New-Clone (Join-Path $C3 'git') 'base3' -Git
$pBase3 = Start-Install (Join-Path $C3 'git') $Cfg3 (Join-Path $C3 'git-setup-run')
Wait-Bounded $pBase3 180
Add-BuildLine (Join-Path $C3 'git') 'B'
$hookB = Join-Path $C3 'hook-b.sh'
Write-ShellRun $hookB (Join-Path $C3 'git') $Cfg3 'sh .git/hooks/post-merge' 'HOOK'
$r3 = Invoke-Overlap $Cfg3 `
    { Start-Install (Join-Path $C3 'a') $Cfg3 (Join-Path $C3 'a-run') } `
    { Start-Shell $hookB (Join-Path $C3 'hook-b-run') } `
    (Join-Path $C3 'hook-b-run')
Test-LockOrder 'cross-path pair' $r3

# ---- lock2: a run given the parent's lock token works under that lock; any other token waits -----------
# merge/install_from_main.sh holds the lock and passes its id as CLAUDE_SETTINGS_LOCK_TOKEN. A token equal
# to line 1 of the lock file lets install.ps1 run at once and leave the lock for its parent. Any other token
# waits like a run with no token, then gives up with one line.
$C5    = Join-Path $Root 'lock2'
$Cfg5  = Join-Path $C5 'claude'
$Lock5 = Join-Path $Cfg5 '.claude-settings-install.lock'
$Tok5  = 'parent-' + [guid]::NewGuid().ToString('N')
New-Clone (Join-Path $C5 'src') 'held'
New-Item -ItemType Directory -Force -Path $Cfg5 | Out-Null
[IO.File]::WriteAllText($Lock5, "$Tok5`n", $Utf8)

$pT = Start-Install (Join-Path $C5 'src') $Cfg5 (Join-Path $C5 'token-run') @{ CLAUDE_SETTINGS_LOCK_TOKEN = $Tok5; CLAUDE_SETTINGS_LOCK_WAIT = '3' }
Wait-Bounded $pT 180
$logT = Get-InstallLog $Cfg5
Check 'lock2: a run with the parent token exits 0' ($pT.ExitCode -eq 0) "exit code '$($pT.ExitCode)'; it did not run under the parent's lock"
Check 'lock2: a run with the parent token writes one start line and one end line' `
    ((Find-PidLines $logT 'start' $pT.Id).Count -eq 1 -and (Find-PidLines $logT 'end' $pT.Id).Count -eq 1) `
    "start lines naming pid $($pT.Id): $((Find-PidLines $logT 'start' $pT.Id).Count); end lines: $((Find-PidLines $logT 'end' $pT.Id).Count)"
Check 'lock2: a run with the parent token leaves the parent lock as it was' ((Get-LockLine $Lock5) -eq $Tok5) "lock line 1 is now '$(Get-LockLine $Lock5)'"

$pW = Start-Install (Join-Path $C5 'src') $Cfg5 (Join-Path $C5 'wrong-run') @{ CLAUDE_SETTINGS_LOCK_TOKEN = "not-$Tok5"; CLAUDE_SETTINGS_LOCK_WAIT = '3' }
Wait-Bounded $pW 180
$logW = Get-InstallLog $Cfg5
$wLockLines = @((Get-RunText (Join-Path $C5 'wrong-run')) -split '\r?\n' | Where-Object { $_ -match 'holds the lock' })
Check 'lock2: a run with a token that does not match exits 1' ($pW.ExitCode -eq 1) "exit code '$($pW.ExitCode)'"
Check 'lock2: a run with a token that does not match prints one lock line' ($wLockLines.Count -eq 1) "lock lines printed: $($wLockLines.Count)"
Check 'lock2: a run with a token that does not match writes no start line' ((Find-PidLines $logW 'start' $pW.Id).Count -eq 0) "start lines naming pid $($pW.Id): $((Find-PidLines $logW 'start' $pW.Id).Count)"
Check 'lock2: a run with a token that does not match leaves the parent lock as it was' ((Get-LockLine $Lock5) -eq $Tok5) "lock line 1 is now '$(Get-LockLine $Lock5)'"

# ---- log3: each installer path logs one start line and one end line, with id and pid ----------
$C4   = Join-Path $Root 'log3'
$Cfg4 = Join-Path $C4 'claude'
New-Clone (Join-Path $C4 'git') 'four' -Git
$p4 = Start-Install (Join-Path $C4 'git') $Cfg4 (Join-Path $C4 'run4')
Wait-Bounded $p4 180
$id4 = Get-LoadedId $Cfg4
$log4 = Get-InstallLog $Cfg4
$ps4s = Find-LogLines $log4 'start' $id4 $p4.Id
$ps4e = Find-LogLines $log4 'end' $id4 $p4.Id
Check 'log3: install.ps1 writes one start line naming its id and pid' ($ps4s.Count -eq 1) "start lines naming id '$id4' and pid $($p4.Id): $($ps4s.Count); log has $($log4.Count) line(s), last: '$($log4 | Select-Object -Last 1)'"
Check 'log3: install.ps1 writes one end line naming its id and pid' ($ps4e.Count -eq 1) "end lines naming id '$id4' and pid $($p4.Id): $($ps4e.Count)"

# names1: the set holds shared_names.py and git_reads.py, which the guard imports, each byte-equal to the flat copy.
# The set should be whole (config-watch-fast-exit), though a flat copy would stand in. Same check for the set the
# post-merge hook lands (id from the hook run).
function Test-NamesInSet([string]$Cfg, [string]$Id, [string]$File = 'shared_names.py') {
    $set  = Join-Path $Cfg "hooks\guard.d\$Id\$File"
    $flat = Join-Path $Cfg "hooks\$File"
    if (-not $Id) { return 'no loaded id (precondition)' }
    if (-not (Test-Path -LiteralPath $set)) { return "missing: $set" }
    if (-not (Test-Path -LiteralPath $flat)) { return "flat copy missing: $flat" }
    if ([IO.File]::ReadAllText($set) -cne [IO.File]::ReadAllText($flat)) { return 'differs from the flat copy' }
    return ''
}
$n4 = Test-NamesInSet $Cfg4 $id4
Check 'names1: install.ps1 lands shared_names.py in guard.d\<id>\, equal to the flat copy' ($n4 -eq '') $n4
$g4 = Test-NamesInSet $Cfg4 $id4 'git_reads.py'
Check 'names1: install.ps1 lands git_reads.py in guard.d\<id>\, equal to the flat copy' ($g4 -eq '') $g4

# The post-merge hook, run from bash so $! is the pid the hook's own $$ reports.
$hook4 = Join-Path $C4 'hook4.sh'
Write-ShellRun $hook4 (Join-Path $C4 'git') $Cfg4 'sh .git/hooks/post-merge' 'HOOK'
$h4 = Start-Shell $hook4 (Join-Path $C4 'hook4-run')
Wait-Bounded $h4 180
$hookText = Get-RunText (Join-Path $C4 'hook4-run')
$hookPid  = if ($hookText -match 'HOOKPID=(\d+)') { [int]$Matches[1] } else { 0 }
$hookExit = if ($hookText -match 'HOOKEXIT=(\d+)') { [int]$Matches[1] } else { -1 }
$id4h = Get-LoadedId $Cfg4
$log4h = Get-InstallLog $Cfg4
$hs = Find-LogLines $log4h 'start' $id4h $hookPid
$he = Find-LogLines $log4h 'end' $id4h $hookPid
Check 'log3: the post-merge hook ran to its end (precondition)' ($hookPid -gt 0 -and $hookExit -ge 0) "hook pid $hookPid, exit $hookExit; output: $(($hookText -split '\r?\n' | Select-Object -Last 3) -join ' | ')"
Check 'log3: the post-merge hook writes one start line naming its id and pid' ($hookPid -gt 0 -and $hs.Count -eq 1) "hook pid $hookPid; start lines naming id '$id4h' and that pid: $($hs.Count)"
Check 'log3: the post-merge hook writes one end line naming its id and pid' ($hookPid -gt 0 -and $he.Count -eq 1) "end lines naming id '$id4h' and pid ${hookPid}: $($he.Count)"
$n4h = if ($id4h -eq $id4) { "hook did not switch the guard set (id $id4h is the install's)" } else { Test-NamesInSet $Cfg4 $id4h }
Check 'names1: the post-merge hook lands shared_names.py in guard.d\<id>\, equal to the flat copy' ($n4h -eq '') $n4h
$g4h = if ($id4h -eq $id4) { "hook did not switch the guard set (id $id4h is the install's)" } else { Test-NamesInSet $Cfg4 $id4h 'git_reads.py' }
Check 'names1: the post-merge hook lands git_reads.py in guard.d\<id>\, equal to the flat copy' ($g4h -eq '') $g4h

# ---- cleanup -------------------------------------------------------------------------------------
try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($EnvSub, $false) } catch { }
Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue

if ($Failed -gt 0) { Write-Host "install-set: $Failed FAIL"; exit 1 }
Write-Host 'install-set: all cases PASS'
exit 0
