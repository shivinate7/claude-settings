# Tests for the install-set ruling (owner ruling 2026-10-15 17:40). An install swaps every guard
# module at once. One install runs at a time. Each installer path logs one start and one end line.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-set.test.ps1
#
# Windows only; elsewhere it prints SKIP and exits 0. Exits 1 on any FAIL. Copy mode only
# (CLAUDE_SETTINGS_FORCE_COPY=1), so the installed guard files are stamped copies. Link mode is not
# covered: a link carries the repo file's placeholder line, so an install cannot make the guard see
# an INSTALL_ID mix there.
#
# Cases. Each is red on a tree without the ruling. Each FAIL line names the bad outcome.
#   swap1   A sibling guard file is held open with read sharing only, so the installer's rename
#           over it is refused, as a reader holding it would refuse it. A second install then stalls
#           mid-swap. No guard run made while that install is alive may be a guard-crash deny. After
#           the install, the guard loads the second install's id.
#   lock1   The second install starts 300 ms after the first, with the same hold, so the first is
#           still alive. The second's guard files must not land while the first is still running.
#           The second must wait, or exit with one clear line about the lock. Two pairs:
#           install.ps1 against install.ps1, and install.ps1 against the git post-merge hook.
#   log3    install.ps1, the post-merge hook and install.sh each log one start line and one end
#           line, naming the install id and the process id.
#
# Every case works under its own folder in a temp root. None touches the real ~/.claude. The
# sampling loops are bounded by a deadline and read local files only; they measure, they do not wait
# on anything outside this machine.
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { Write-Host 'SKIP: install set (Windows only)'; exit 0 }

$Here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Utf8    = New-Object Text.UTF8Encoding($false)
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

# The text of every guard*.py under a config dir, wherever the installer put it. Unreadable files are skipped.
function Get-GuardTexts([string]$Cfg) {
    $out = @()
    foreach ($f in @(Get-ChildItem -LiteralPath $Cfg -Recurse -File -Filter 'guard*.py' -ErrorAction SilentlyContinue)) {
        try { $out += Read-Shared $f.FullName } catch { }
    }
    return $out
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

# A clone folder: install.ps1 and install.sh, the repo's guard files each with a build line appended,
# and a settings.json and CLAUDE.md. With -Skills N it also lands N skill folders after the hooks, so
# an install runs long enough to overlap another. With -Git it is a git repository on main.
function New-Clone([string]$Dir, [string]$Build, [int]$Skills = 0, [switch]$Git) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Dir 'hooks') | Out-Null
    Copy-Item -LiteralPath (Join-Path $Here 'install.ps1') -Destination (Join-Path $Dir 'install.ps1')
    Copy-Item -LiteralPath (Join-Path $Here 'install.sh') -Destination (Join-Path $Dir 'install.sh')
    [IO.File]::WriteAllText((Join-Path $Dir 'CLAUDE.md'), "# fixture $Build`n", $Utf8)
    [IO.File]::WriteAllText((Join-Path $Dir 'settings.json'), "{}`n", $Utf8)
    $lands = if ($Skills -gt 0) { "hooks`nskills`n" } else { "hooks`n" }
    [IO.File]::WriteAllText((Join-Path $Dir 'landed-dirs.txt'), $lands, $Utf8)
    foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $Here 'hooks') -File | Where-Object { $_.Name -ceq 'guard.py' -or $_.Name -clike 'guard_*.py' })) {
        $text = [IO.File]::ReadAllText($f.FullName)
        [IO.File]::WriteAllText((Join-Path $Dir ('hooks\' + $f.Name)), $text + "`n# build $Build`n", $Utf8)
    }
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
function Start-Install([string]$Clone, [string]$Cfg, [string]$Out) {
    $saved = Set-Env @{
        CLAUDE_CONFIG_DIR = $Cfg; CLAUDE_SETTINGS_FORCE_COPY = '1'
        CLAUDE_SETTINGS_USER_ENV_KEY = "HKCU:\$EnvSub"; USERPROFILE = $NoGit }
    try {
        $proc = Start-Process -FilePath $PsHost -PassThru -NoNewWindow -WorkingDirectory $NoGit `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $Clone 'install.ps1') + '"')) `
            -RedirectStandardOutput "$Out.out.txt" -RedirectStandardError "$Out.err.txt"
        $null = $proc.Handle   # cache the handle now: without it, ExitCode reads back empty after exit
        return $proc
    } finally { Restore-Env $saved }
}

# Writes a bash script that runs one post-merge hook, or install.sh, from a clone, and prints the pid
# of that child as bash sees it ($!). The child's own $$ is the same number.
function Write-ShellRun([string]$Path, [string]$GitDir, [string]$Cfg, [string]$Command, [string]$Label) {
    $g = $GitDir -replace '\\', '/'
    $c = $Cfg -replace '\\', '/'
    # install.sh appends a PATH line to $HOME's rc file when its marker is missing, so HOME is a scratch folder.
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

# The install log in a config dir, as lines. Missing means no lines.
function Get-InstallLog([string]$Cfg) {
    $path = Join-Path $Cfg 'claude-settings-install.log'
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    try { return @((Read-Shared $path) -split '\r?\n' | Where-Object { $_ -ne '' }) } catch { return @() }
}

# Numbers of 8 or more digits in a line. An install id is one of them.
function Get-IdTokens([string]$Line) {
    return @([regex]::Matches($Line, '\d{8,}') | ForEach-Object { $_.Value })
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
# Overlap is forced: the first install holds the sibling file, and it runs a skills tree after the
# hooks. The sampler records when the second install's guard text first lands, and when the first exits.
function Invoke-Overlap([string]$Cfg, [scriptblock]$StartA, [scriptblock]$StartB, [string]$OutB) {
    $hold = Hold-File (Join-Path $Cfg 'hooks\guard_core.py')
    $tA = Get-Date
    $pA = & $StartA
    Start-Sleep -Milliseconds 300
    $aAliveAtB = -not $pA.HasExited
    $pB = & $StartB
    $bFirst = $null; $aExit = $null; $released = $false
    $deadline = (Get-Date).AddSeconds(150)
    while ((-not $pA.HasExited -or -not $pB.HasExited) -and (Get-Date) -lt $deadline) {
        $now = Get-Date
        if (-not $released -and ($now - $tA).TotalSeconds -ge 9) { $hold.Close(); $released = $true }
        if ($pA.HasExited -and -not $aExit) { $aExit = $now }
        if (-not $bFirst) {
            foreach ($text in (Get-GuardTexts $Cfg)) { if ($text -match '# build B') { $bFirst = $now; break } }
        }
        Start-Sleep -Milliseconds 50
    }
    if (-not $released) { $hold.Close() }
    Wait-Bounded $pA 60
    Wait-Bounded $pB 60
    if (-not $aExit) { $aExit = Get-Date }
    $bLines = @((Get-RunText $OutB) -split '\r?\n' | Where-Object { $_ -match '(?i)lock|another install|already running|waiting' })
    return @{ AAlive = $aAliveAtB; BFirst = $bFirst; AExit = $aExit; BLockLines = $bLines.Count; BExit = $pB.ExitCode }
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
Check 'lock1: precondition, install A was still alive when install B started (install.ps1 pair)' $r2.AAlive 'install A had already exited; the case proves nothing'
if ($r2.BFirst) {
    $lead2 = ($r2.AExit - $r2.BFirst).TotalSeconds
    Check 'lock1: install B guard files did not land while install A ran (install.ps1 pair)' ($lead2 -lt 1.0) ("install B's guard files landed {0:N1} s before install A exited" -f $lead2)
} else {
    Check 'lock1: install B waited or exited with one clear lock line (install.ps1 pair)' ($r2.BLockLines -eq 1) "install B wrote no guard file and printed $($r2.BLockLines) lock line(s)"
}

# Pair 2: install.ps1 against the git post-merge hook (cross-path). The hook is the one install.ps1
# wrote into the git clone, and it copies that clone's working tree, marked build B.
$C3   = Join-Path $Root 'lock1-hook'
$Cfg3 = Join-Path $C3 'claude'
New-Clone (Join-Path $C3 'a') 'A' -Skills 60
New-Clone (Join-Path $C3 'git') 'B' -Git
$pBase3 = Start-Install (Join-Path $C3 'git') $Cfg3 (Join-Path $C3 'git-setup-run')
Wait-Bounded $pBase3 180
$hookB = Join-Path $C3 'hook-b.sh'
Write-ShellRun $hookB (Join-Path $C3 'git') $Cfg3 'sh .git/hooks/post-merge' 'HOOK'
$r3 = Invoke-Overlap $Cfg3 `
    { Start-Install (Join-Path $C3 'a') $Cfg3 (Join-Path $C3 'a-run') } `
    { Start-Shell $hookB (Join-Path $C3 'hook-b-run') } `
    (Join-Path $C3 'hook-b-run')
Check 'lock1: precondition, install A was still alive when the hook started (cross-path pair)' $r3.AAlive 'install A had already exited; the case proves nothing'
if ($r3.BFirst) {
    $lead3 = ($r3.AExit - $r3.BFirst).TotalSeconds
    Check 'lock1: the hook guard files did not land while install A ran (cross-path pair)' ($lead3 -lt 1.0) ("the hook's guard files landed {0:N1} s before install A exited" -f $lead3)
} else {
    Check 'lock1: the hook waited or exited with one clear lock line (cross-path pair)' ($r3.BLockLines -eq 1) "the hook wrote no guard file and printed $($r3.BLockLines) lock line(s)"
}

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

# install.sh, from the same clone, run from bash so $! is its $$. Local mode stamps no id, so the start
# and end lines must share one id-like number (8 or more digits) instead.
$sh4 = Join-Path $C4 'sh4.sh'
Write-ShellRun $sh4 (Join-Path $C4 'git') $Cfg4 'bash ./install.sh' 'SH'
$s4 = Start-Shell $sh4 (Join-Path $C4 'sh4-run')
Wait-Bounded $s4 180
$shText = Get-RunText (Join-Path $C4 'sh4-run')
$shPid  = if ($shText -match 'SHPID=(\d+)') { [int]$Matches[1] } else { 0 }
$shExit = if ($shText -match 'SHEXIT=(\d+)') { [int]$Matches[1] } else { -1 }
$log4s  = Get-InstallLog $Cfg4
$sStart = @($log4s | Where-Object { $_ -match '(?i)\bstart\b' -and $_ -match "(?<!\d)$shPid(?!\d)" })
$sEnd   = @($log4s | Where-Object { $_ -match '(?i)\bend\b' -and $_ -match "(?<!\d)$shPid(?!\d)" })
$sharedId = $false
if ($sStart.Count -eq 1 -and $sEnd.Count -eq 1) {
    $endIds = Get-IdTokens $sEnd[0]
    $sharedId = (@(Get-IdTokens $sStart[0] | Where-Object { $endIds -contains $_ }).Count -ge 1)
}
Check 'log3: install.sh ran to its end (precondition)' ($shPid -gt 0 -and $shExit -eq 0) "install.sh pid $shPid, exit $shExit; output: $(($shText -split '\r?\n' | Select-Object -Last 3) -join ' | ')"
Check 'log3: install.sh writes one start line naming its id and pid' ($shPid -gt 0 -and $sStart.Count -eq 1) "install.sh pid $shPid; start lines naming that pid: $($sStart.Count)"
Check 'log3: install.sh writes one end line, with the same id as its start line' ($shPid -gt 0 -and $sEnd.Count -eq 1 -and $sharedId) "install.sh pid ${shPid}: end lines naming it: $($sEnd.Count); shared id: $sharedId"

# ---- cleanup -------------------------------------------------------------------------------------
try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($EnvSub, $false) } catch { }
Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue

if ($Failed -gt 0) { Write-Host "install-set: $Failed FAIL"; exit 1 }
Write-Host 'install-set: all cases PASS'
exit 0
