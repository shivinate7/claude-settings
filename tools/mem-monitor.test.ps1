# Static checks for tools/mem-monitor.ps1, the manual Windows memory monitor. A person runs it by
# hand in its own PowerShell window. No hook may start it and no installer may copy it.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\mem-monitor.test.ps1
#
# This is the owner's command: Windows PowerShell 5.1. The checks are verified on 5.1 only.
#
# Every check but the last group reads text only. The loop has no end, so a run starts the monitor
# only with -Log set to a file in a temp folder, and kills it when its answer is in.
#
#   cols    The script's [pscustomobject] row has exactly the property names in $Columns, in that
#           order. PowerShell's own parser finds the names, so a name inside a comment, a string
#           or a here-string never counts. The fixture cases below pin that.
#   landed  landed-dirs.txt has no tools entry. install.sh and install.ps1 name no tools path
#           and no mem-monitor.
#   hooks   No tracked settings or hooks file mentions mem-monitor.
#   name    The script's param block, run alone, gives a default -Log of
#           <USERPROFILE>\claude-mem-log-yyyyMMdd-HHmmss.csv, stamped with the time of the run. Any OS.
#   header  Windows only (the monitor reads WMI). The monitor runs against temp logs:
#           a log whose header is not the $Columns, in order: the script stops with a message and the
#           file is byte for byte unchanged (two cases: one column short, and the last two swapped);
#           a log with the right header: the script appends rows;
#           no log yet: the script creates one with the right header;
#           a zero-byte log is a fresh log: the header line, then rows (two are awaited), and no
#           other line.
#           No wait is longer than $WaitSec. A run that ends by itself takes about 2.5 s on a
#           fast PC (measured, 5.1); the limit is met only when a check is about to fail.
$ErrorActionPreference = 'Stop'

# The CSV header, in order. Change this list only together with the script's row.
$Columns = @('Time', 'InUseGB', 'PagedGB', 'NonpagedGB', 'CommitGB', 'Procs', 'MaxPID', 'Shells',
             'MaxShHandles', 'TotalShHandles', 'Python', 'ClaudeProcs')

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here

$Failed = 0
function Check([string]$name, [bool]$ok, [string]$why) {
    if ($ok) { Write-Host "PASS: $name" } else { Write-Host "FAIL: ${name}: $why"; $script:Failed++ }
}

# Every [pscustomobject]@{...} literal in the text that has a Time key, as an array of key lists in
# source order. [pscustomobject][ordered]@{...} counts too.
function Get-Rows([string]$Text) {
    $errs = $null
    $tree = [System.Management.Automation.Language.Parser]::ParseInput($Text, [ref]$null, [ref]$errs)
    $rows = New-Object System.Collections.ArrayList
    if (-not $errs -or $errs.Count -eq 0) {
        $casts = $tree.FindAll({ param($n) $n -is [System.Management.Automation.Language.ConvertExpressionAst] }, $true)
        foreach ($c in $casts) {
            if (@('pscustomobject', 'System.Management.Automation.PSCustomObject') -notcontains $c.Type.TypeName.Name) { continue }
            $h = $c.Child
            while ($h -is [System.Management.Automation.Language.ConvertExpressionAst] -and $h.Type.TypeName.Name -eq 'ordered') { $h = $h.Child }
            if ($h -isnot [System.Management.Automation.Language.HashtableAst]) { continue }
            $keys = @(foreach ($p in $h.KeyValuePairs) {
                if ($p.Item1 -is [System.Management.Automation.Language.StringConstantExpressionAst]) { $p.Item1.Value }
                else { '<' + $p.Item1.Extent.Text + '>' }
            })
            if ($keys -contains 'Time') { [void]$rows.Add($keys) }
        }
    }
    return @{ Errors = $errs; Rows = $rows }
}

# '' when the script text holds exactly one Time row and its names equal $Columns, else the reason.
function Test-MonitorText([string]$Text) {
    $r = Get-Rows $Text
    if ($r.Errors -and $r.Errors.Count -gt 0) { return "parse error: $($r.Errors[0].Message)" }
    if ($r.Rows.Count -eq 0) { return 'no [pscustomobject]@{...} literal with a Time key' }
    if ($r.Rows.Count -gt 1) { return "$($r.Rows.Count) [pscustomobject] literals have a Time key; the row must be the only one" }
    $got = $r.Rows[0] -join ','
    $want = $Columns -join ','
    if ($got -cne $want) { return "property names are '$got', want '$want'" }
    return ''
}

# The names landed-dirs.txt gives the installers: `#` to end of line cut, blanks dropped.
function Get-LandedNames([string]$Text) {
    @($Text -split "`r?`n" | ForEach-Object { ($_ -replace '#.*', '').Trim().TrimEnd('/', '\') } | Where-Object { $_ -ne '' })
}

# A tools path or the monitor's name in installer text. `tools` counts only right after a slash or a
# quote: the bare word is prose, and build-tools/ or devtools\ are other folders.
$InstallerHit = '(?i)(?<=[/\\''"])tools(?![\w.-])|mem[-_]?monitor'

# ---- fixtures: the extractor must not be fooled by text that only looks like a row ----------------

function Row([string[]]$Names) { '$row = [pscustomobject]@{ ' + (($Names | ForEach-Object { "$_ = 1" }) -join '; ') + ' }' }

$n = $Columns.Count
$swapped = $Columns.Clone(); $swapped[$n - 2], $swapped[$n - 1] = $swapped[$n - 1], $swapped[$n - 2]
$why = Test-MonitorText (Row $Columns)
Check 'fixture: the exact list passes' ($why -eq '') $why
Check 'fixture: the last two names swapped fail' ((Test-MonitorText (Row $swapped)) -like "property names are*") 'a reorder passed'
Check 'fixture: the last name dropped fails' ((Test-MonitorText (Row $Columns[0..($n - 2)])) -like "property names are*") 'a short list passed'
Check 'fixture: an extra name fails' ((Test-MonitorText (Row ($Columns + 'Extra'))) -like "property names are*") 'a long list passed'
Check 'fixture: lower-case names fail' ((Test-MonitorText (Row ($Columns | ForEach-Object { $_.ToLower() }))) -like "property names are*") 'a case change passed'
Check 'fixture: [ordered] inside the cast is read' ((Test-MonitorText ('$row = [pscustomobject][ordered]@{ ' + (($Columns | ForEach-Object { "$_ = 1" }) -join '; ') + ' }')) -eq '') 'ordered row not read'
Check 'fixture: no literal fails' ((Test-MonitorText '$x = 1') -like 'no [[]pscustomobject]*') 'empty script passed'
Check 'fixture: a second Time row fails' ((Test-MonitorText ((Row $Columns) + "`n" + (Row $Columns))) -like '2 *') 'two rows passed'
Check 'fixture: a second row with no Time key is ignored' ((Test-MonitorText ((Row $Columns) + "`n" + '$sum = [pscustomobject]@{ Total = 1 }')) -eq '') 'summary object counted'
Check 'fixture: a parse error fails' ((Test-MonitorText '$x = @{') -like 'parse error*') 'broken script passed'

# Comment openers inside strings, a lone quote in a comment, a multi-line string, a here-string:
# every decoy below holds a Time row. Only the last line is the real one.
$trap = @'
# don't count [pscustomobject]@{ Time = 1; Decoy = 2 }
<# block comment with a lone ' quote
[pscustomobject]@{ Time = 3; Block = 4 } #>
$a = 'a # not a comment <# nor this #> // or /* this */'
$b = "multi
line [pscustomobject]@{ Time = 5; Str = 6 }
it's text"
$c = @"
[pscustomobject]@{ Time = 7; Here = 8 }
"@
$row = [pscustomobject]@{ Time = 'x'; Real = 1; 'Quoted' = 2 }
'@
$t = Get-Rows $trap
Check 'fixture: comments, strings and here-strings hold no row' ($t.Rows.Count -eq 1 -and ($t.Rows[0] -join ',') -ceq 'Time,Real,Quoted') ("rows: " + (($t.Rows | ForEach-Object { $_ -join ',' }) -join ' | '))

$l = Get-LandedNames "agents`n# tools`nhooks # tools`n  bin  `r`n"
Check 'fixture: landed names drop comments and blanks' (($l -join ',') -ceq 'agents,hooks,bin') ($l -join ',')
Check 'fixture: a tools entry is found with a comment, a slash, or other case' ((@(Get-LandedNames "Tools/ # why") -contains 'tools') -and (@(Get-LandedNames "tools # why") -contains 'tools')) 'tools entry missed'
foreach ($hit in @('cp -r "$SRC/tools" x', 'Copy-Item .\tools\x y', "land_dir 'tools'", 'cp mem-monitor.ps1 x', 'Copy-Item mem_monitor.ps1 x')) {
    Check "fixture: installer text '$hit' is a hit" ([regex]::IsMatch($hit, $InstallerHit)) 'not found'
}
foreach ($miss in @('# tools that read them by path', 'build-tools/x', 'devtools\x', 'Tool names', 'monitor of mem')) {
    Check "fixture: installer text '$miss' is no hit" (-not [regex]::IsMatch($miss, $InstallerHit)) 'false alarm'
}

# ---- the real files ------------------------------------------------------------------------------

$Script = Join-Path $Here 'mem-monitor.ps1'
if (Test-Path -LiteralPath $Script -PathType Leaf) {
    Check 'tools/mem-monitor.ps1 exists' $true ''
    $why = Test-MonitorText ([IO.File]::ReadAllText($Script))
    Check 'tools/mem-monitor.ps1: row property names are the CSV columns, in order' ($why -eq '') $why
} else {
    Check 'tools/mem-monitor.ps1 exists' $false "no file at $Script"
}

$landed = Get-LandedNames ([IO.File]::ReadAllText((Join-Path $Root 'landed-dirs.txt')))
Check 'landed-dirs.txt: lists names, none of them tools' ($landed.Count -gt 0 -and $landed -notcontains 'tools') ('landed: ' + ($landed -join ','))
foreach ($f in @('install.sh', 'install.ps1')) {
    $m = [regex]::Match([IO.File]::ReadAllText((Join-Path $Root $f)), $InstallerHit)
    Check "${f}: names no tools path and no mem-monitor" (-not $m.Success) "found '$($m.Value)'"
}

# git lists the tracked files only, so an untracked scratch copy never counts.
$json = @(& git -C $Root ls-files -- '*settings*.json' '*hooks.json')
Check 'git lists settings.json and at least one hooks.json' ($LASTEXITCODE -eq 0 -and $json -contains 'settings.json' -and @($json | Where-Object { $_ -like '*hooks.json' }).Count -gt 0) ('listed: ' + ($json -join ','))
foreach ($f in $json) {
    $m = [regex]::Match([IO.File]::ReadAllText((Join-Path $Root $f)), 'mem[-_]?monitor', 'IgnoreCase')
    Check "${f}: no mem-monitor entry" (-not $m.Success) "found '$($m.Value)'"
}

# ---- name: the default -Log is a new, time-stamped file each run ---------------------------------

# '' when the script's own param block gives a default -Log of <USERPROFILE>\claude-mem-log-<stamp>.csv
# with the stamp within five minutes of now (local or UTC), else the reason. The param block runs
# alone, with USERPROFILE set to a fake folder, so nothing else in the script runs. The root
# ParamBlock is the script's own: a param block in a function or in a comment never counts.
$FakeProfile = Join-Path ([IO.Path]::GetTempPath()) 'mem-monitor-profile'
function Test-DefaultLog([string]$Text) {
    $errs = $null
    $tree = [System.Management.Automation.Language.Parser]::ParseInput($Text, [ref]$null, [ref]$errs)
    if ($errs -and $errs.Count -gt 0) { return "parse error: $($errs[0].Message)" }
    if (-not $tree.ParamBlock) { return 'no param block' }
    $saved = $env:USERPROFILE
    $env:USERPROFILE = $FakeProfile
    try { $got = [string](& ([scriptblock]::Create($tree.ParamBlock.Extent.Text + "`n" + '$Log'))) }
    finally { $env:USERPROFILE = $saved }
    $m = [regex]::Match($got, '^' + [regex]::Escape($FakeProfile) + '[\\/]claude-mem-log-(\d{8}-\d{6})\.csv$')
    if (-not $m.Success) { return "default Log is '$got', want <USERPROFILE>\claude-mem-log-yyyyMMdd-HHmmss.csv" }
    try { $stamp = [datetime]::ParseExact($m.Groups[1].Value, 'yyyyMMdd-HHmmss', [Globalization.CultureInfo]::InvariantCulture) }
    catch { return "the stamp '$($m.Groups[1].Value)' is not a date and time" }
    $slack = [TimeSpan]::FromMinutes(5)
    if (([datetime]::Now - $stamp).Duration() -lt $slack -or ([datetime]::UtcNow - $stamp).Duration() -lt $slack) { return '' }
    return "the stamp '$($m.Groups[1].Value)' is not the time of this run"
}

function Param-Of([string]$LogDefault) { 'param([string]$Log = ' + $LogDefault + ', [int]$Seconds = 5, [int]$Minutes = 0)' }
$stampNow = '"$env:USERPROFILE\claude-mem-log-$(Get-Date -Format ''yyyyMMdd-HHmmss'').csv"'
$why = Test-DefaultLog (Param-Of $stampNow)
Check 'fixture: a time-stamped default passes' ($why -eq '') $why
Check 'fixture: a UTC stamp passes' ((Test-DefaultLog (Param-Of '"$env:USERPROFILE\claude-mem-log-$((Get-Date).ToUniversalTime().ToString(''yyyyMMdd-HHmmss'')).csv"')) -eq '') 'a UTC stamp failed'
Check 'fixture: the fixed name fails' ((Test-DefaultLog (Param-Of '"$env:USERPROFILE\claude-mem-log.csv"')) -like 'default Log is*') 'a fixed name passed'
Check 'fixture: a frozen stamp fails' ((Test-DefaultLog (Param-Of '"$env:USERPROFILE\claude-mem-log-20200101-000000.csv"')) -like '*not the time of this run') 'a frozen stamp passed'
Check 'fixture: another folder fails' ((Test-DefaultLog (Param-Of '"C:\other\claude-mem-log-$(Get-Date -Format ''yyyyMMdd-HHmmss'').csv"')) -like 'default Log is*') 'another folder passed'
Check 'fixture: no param block fails' ((Test-DefaultLog '$Log = 1') -eq 'no param block') 'a script with no param block passed'
Check 'fixture: a param block with no Log fails' ((Test-DefaultLog 'param([int]$Seconds = 5)') -like 'default Log is*') 'no Log parameter passed'

# Decoy param blocks in comments, a function and a here-string, and a `)` and a lone quote in text.
# The real default is the stamped one, so only the script's own param block gives ''.
$paramTrap = @'
# param([string]$Log = 'decoy') ) don't
<# param($Log = 'block decoy')
it's text #>
param(
    [string]$Log = "$env:USERPROFILE\claude-mem-log-$(Get-Date -Format 'yyyyMMdd-HHmmss').csv",   # a ) and a lone ' here
    [int]$Seconds = 5
)
function f { param($Log = 'nested decoy') }
$h = @"
param($Log = 'here-string decoy')
"@
'@
$why = Test-DefaultLog $paramTrap
Check 'fixture: decoy param blocks in comments, a function and a here-string are ignored' ($why -eq '') $why

if (Test-Path -LiteralPath $Script -PathType Leaf) {
    $why = Test-DefaultLog ([IO.File]::ReadAllText($Script))
    Check 'tools/mem-monitor.ps1: the default -Log is a new time-stamped file' ($why -eq '') $why
}

# ---- header: a log whose header differs is never written to (Windows only) --------------------------

function Read-Shared([string]$Path) {
    try {
        $share = [IO.FileShare]([int][IO.FileShare]::ReadWrite -bor [int][IO.FileShare]::Delete)
        $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
        try { return (New-Object IO.StreamReader($fs)).ReadToEnd() } finally { $fs.Close() }
    } catch { return '' }
}

$Quoted = '"' + ($Columns -join '","') + '"'
$Short  = '"' + (($Columns | Where-Object { $_ -ne 'Python' }) -join '","') + '"'
$Swap   = '"' + (($swapped) -join '","') + '"'
$Row11  = '"10:48:06","29","1.2","1.63","25.3","383","41592","0","0","0","0"'
$Row12  = '"10:48:06","29","1.2","1.63","25.3","383","41592","0","0","0","0","0"'
if ($env:OS -ne 'Windows_NT') {
    Write-Host 'SKIP: header checks run the monitor, which reads WMI (Windows only)'
} elseif (-not (Test-Path -LiteralPath $Script -PathType Leaf)) {
    Check 'tools/mem-monitor.ps1: header checks' $false 'no script to run'
} else {
    $PsHost = (Get-Process -Id $PID).Path
    $WaitSec = 30   # an upper bound, spent only when a check is about to fail; cold CI runners are unmeasured
    $Tmp =Join-Path ([IO.Path]::GetTempPath()) ('mem-monitor-test-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
    $started = @()
    try {
        # One run, -Minutes 1 so it would end by itself; the checks below kill it first or watch it stop.
        function Start-Monitor([string]$Log) {
            $o = Join-Path $Tmp ([guid]::NewGuid().ToString('N'))
            $argv = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $Script + '"'), '-Log', ('"' + $Log + '"'), '-Seconds', '1', '-Minutes', '1')
            $p = Start-Process -FilePath $PsHost -ArgumentList $argv -PassThru -NoNewWindow -RedirectStandardOutput "$o.out" -RedirectStandardError "$o.err"
            $null = $p.Handle
            $script:started += $p
            return @{ Proc = $p; Out = "$o.out"; Err = "$o.err"; Log = $Log }
        }
        function New-Log([string]$Name, [string]$Text) {
            $p = Join-Path $Tmp $Name
            [IO.File]::WriteAllText($p, $Text, (New-Object Text.UTF8Encoding($false)))
            return $p
        }
        $badShort = New-Log 'short.csv' ($Short + "`r`n" + $Row11 + "`r`n")
        $badSwap  = New-Log 'swap.csv' ($Swap + "`r`n" + $Row12 + "`r`n")
        $goodText = $Quoted + "`r`n"
        $good     = New-Log 'good.csv' $goodText
        $zero     = New-Log 'zero.csv' ''
        $fresh    = Join-Path $Tmp 'fresh.csv'
        $before   = @{ short = (Read-Shared $badShort); swap = (Read-Shared $badSwap) }
        Check 'the zero-byte log starts at zero bytes' ((Get-Item -LiteralPath $zero).Length -eq 0) 'the fixture file is not empty'

        $deadline = (Get-Date).AddSeconds($WaitSec)
        $runs = @{ short = Start-Monitor $badShort; swap = Start-Monitor $badSwap; good = Start-Monitor $good; fresh = Start-Monitor $fresh; zero = Start-Monitor $zero }

        foreach ($k in 'short', 'swap') {
            $m = $runs[$k]
            $left = [int][Math]::Max(0, ($deadline - (Get-Date)).TotalMilliseconds)
            $ended = $m.Proc.WaitForExit($left)
            if (-not $ended) { try { $m.Proc.Kill() } catch { }; $null = $m.Proc.WaitForExit(5000) }
            $out = (Read-Shared $m.Out) + (Read-Shared $m.Err)
            $out = $out.Substring(0, [Math]::Min(120, $out.Length))
            $label = @{ short = 'a log with one column short'; swap = 'a log with the last two columns swapped' }[$k]
            Check "${label}: the script stops on its own" $ended "still running after $WaitSec s, so it kept writing; killed"
            Check "${label}: it stops with a message" ($ended -and ($m.Proc.ExitCode -ne 0 -or $out -match '(?i)header|column')) "exit $($m.Proc.ExitCode), output '$out'"
            Check "${label}: the file is unchanged" ((Read-Shared $m.Log) -ceq $before[$k]) 'the script wrote to it'
        }

        foreach ($k in 'good', 'fresh', 'zero') {
            $m = $runs[$k]
            $need = if ($k -eq 'zero') { 2 } else { 1 }
            while ((Get-Date) -lt $deadline -and @(Read-Shared $m.Log | ConvertFrom-Csv).Count -lt $need -and -not $m.Proc.HasExited) { Start-Sleep -Milliseconds 100 }
            $text = Read-Shared $m.Log
            $rows = @($text | ConvertFrom-Csv)
            $names = if ($rows.Count -gt 0) { $rows[0].PSObject.Properties.Name -join ',' } else { '' }
            $label = @{ good = 'a log with the right header'; fresh = 'no log yet'; zero = 'a zero-byte log' }[$k]
            Check "${label}: the script appends a row under the right header" ($rows.Count -ge $need -and $names -ceq ($Columns -join ',')) "rows $($rows.Count), want $need, header '$names', exit $(if ($m.Proc.HasExited) { $m.Proc.ExitCode } else { 'none, still running' })"
            if ($k -eq 'zero') {
                # One trailing newline is cut. Any other line that is not the header, then 12-field rows, fails.
                $lines = @(($text -replace "`r?`n$", '') -split "`r?`n")
                $stray = @($lines | Select-Object -Skip 1 | Where-Object { $_ -notmatch '^"\d\d:\d\d:\d\d"(,"[^"]*"){11}$' })
                Check "${label}: the file is the header line, then rows, and nothing else" ($lines.Count -ge ($need + 1) -and $lines[0] -ceq $Quoted -and $stray.Count -eq 0) "lines $($lines.Count), first '$($lines[0])', other lines '$($stray -join ' | ')'"
            }
        }
        Check 'a log with the right header: the old text is kept' ((Read-Shared $good).StartsWith($goodText)) 'the old text changed'
    } finally {
        foreach ($p in $started) { if (-not $p.HasExited) { try { $p.Kill() } catch { } } }
        Start-Sleep -Milliseconds 500
        Remove-Item -Recurse -Force -LiteralPath $Tmp -ErrorAction SilentlyContinue
    }
}

if ($Failed -gt 0) { Write-Host "$Failed FAIL"; exit 1 }
Write-Host 'all checks passed'
exit 0
