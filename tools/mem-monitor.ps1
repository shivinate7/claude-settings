# tools/mem-monitor.ps1 - a manual memory and process monitor for Windows.
# A person runs it by hand. It is never a hook and no installer copies it.
# Run it in its own PowerShell window, never inside a Claude session.
# Usage: powershell -ExecutionPolicy Bypass -File tools\mem-monitor.ps1 [-Log path] [-Seconds 5] [-Minutes 0]
# Each run writes a new log file, named with the start time. If -Log names a file whose header is
# not the 12 columns below, the script stops and writes nothing.
param(
  [string]$Log = "$env:USERPROFILE\claude-mem-log-$(Get-Date -Format 'yyyyMMdd-HHmmss').csv",
  [int]$Seconds = 5,
  [int]$Minutes = 0   # 0 = run until Ctrl+C
)
$cols = 'Time','InUseGB','PagedGB','NonpagedGB','CommitGB','Procs','MaxPID','Shells','MaxShHandles','TotalShHandles','Python','ClaudeProcs'
if ((Test-Path -LiteralPath $Log) -and (Get-Item -LiteralPath $Log).Length -gt 0) {
  $first = (Get-Content -LiteralPath $Log -TotalCount 1) -replace '"',''
  if ($first -cne ($cols -join ',')) {
    [Console]::Error.WriteLine("mem-monitor: the header of $Log is not the 12 expected columns. Nothing written.")
    exit 1
  }
}
$total = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
$end = if ($Minutes -gt 0) { (Get-Date).AddMinutes($Minutes) } else { [datetime]::MaxValue }
while ((Get-Date) -lt $end) {
  $m   = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
  $all = Get-Process
  $sh  = @($all | Where-Object { $_.Name -in 'sh','bash' })
  $cl  = @($all | Where-Object { $_.Name -eq 'claude' })
  $py  = @($all | Where-Object { $_.Name -like 'python*' })
  $row = [pscustomobject]@{
    Time           = (Get-Date).ToString('HH:mm:ss')
    InUseGB        = [math]::Round(($total - $m.AvailableBytes)/1GB,1)
    PagedGB        = [math]::Round($m.PoolPagedBytes/1GB,2)
    NonpagedGB     = [math]::Round($m.PoolNonpagedBytes/1GB,2)
    CommitGB       = [math]::Round($m.CommittedBytes/1GB,1)
    Procs          = $all.Count
    MaxPID         = ($all | Measure-Object Id -Maximum).Maximum
    Shells         = $sh.Count
    MaxShHandles   = [int]($sh | Measure-Object Handles -Maximum).Maximum
    TotalShHandles = [int]($sh | Measure-Object Handles -Sum).Sum
    Python         = $py.Count
    ClaudeProcs    = $cl.Count
  }
  $row | Export-Csv $Log -Append -NoTypeInformation
  Write-Host ("{0}  InUse {1}GB  Paged {2}  NonPaged {3}  Commit {4}  procs {5}  maxPID {6}  sh {7}  maxH {8}  totH {9}  py {10}  claude {11}" -f `
    $row.Time,$row.InUseGB,$row.PagedGB,$row.NonpagedGB,$row.CommitGB,$row.Procs,$row.MaxPID,$row.Shells,$row.MaxShHandles,$row.TotalShHandles,$row.Python,$row.ClaudeProcs)
  Start-Sleep $Seconds
}
