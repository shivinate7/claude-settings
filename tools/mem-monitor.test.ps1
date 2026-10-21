# Static checks for tools/mem-monitor.ps1, the manual Windows memory monitor. A person runs it by
# hand in its own PowerShell window. No hook may start it and no installer may copy it.
#
#   pwsh -NoProfile -File .\tools\mem-monitor.test.ps1      (PowerShell 5.1 and 7, any OS)
#
# The checks read text only. They never start the monitor: its loop has no end, and a run
# appends rows to a log file on this machine.
#
#   cols    The script's [pscustomobject] row has exactly the property names in $Columns, in that
#           order. PowerShell's own parser finds the names, so a name inside a comment, a string
#           or a here-string never counts. The fixture cases below pin that.
#   landed  landed-dirs.txt has no tools entry. install.sh and install.ps1 name no tools path
#           and no mem-monitor.
#   hooks   No tracked settings or hooks file mentions mem-monitor.
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

if ($Failed -gt 0) { Write-Host "$Failed FAIL"; exit 1 }
Write-Host 'all checks passed'
exit 0
