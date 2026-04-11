param(
  [switch]$AutoStart
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot "common.ps1")

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

[System.Windows.Forms.Application]::EnableVisualStyles()

$script:root = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:runtimeDir = Join-Path $script:root ".runtime"
$script:logDir = Join-Path $script:runtimeDir "logs"
$script:devProcessStateFile = Join-Path $script:runtimeDir "dev-processes.json"
$script:monitorCloseFlagFile = Join-Path $script:runtimeDir "dev-monitor.close.flag"
$script:startScriptPath = Join-Path $PSScriptRoot "start-dev.ps1"
$script:stopScriptPath = Join-Path $PSScriptRoot "stop-dev.ps1"
$script:frontendUrl = "http://127.0.0.1:5174"
$script:backendUrl = "http://127.0.0.1:8014"
$script:launcherOutLog = Join-Path $script:logDir "launcher.out.log"
$script:launcherErrLog = Join-Path $script:logDir "launcher.err.log"
$script:closerOutLog = Join-Path $script:logDir "closer.out.log"
$script:closerErrLog = Join-Path $script:logDir "closer.err.log"
$script:launcherProcess = $null
$script:stopProcess = $null
$script:lastLauncherExitCode = $null
$script:lastCloserExitCode = $null
$script:lastStatusGridSignature = ""
$script:lastStatusText = ""
$script:lastLogSnapshots = @{}

function Ensure-RuntimeDirectory {
  foreach ($path in @($script:runtimeDir, $script:logDir)) {
    if (-not (Test-Path $path)) {
      New-Item -ItemType Directory -Path $path | Out-Null
    }
  }
}

function Reset-LogFile {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  Ensure-RuntimeDirectory
  if (Test-Path $Path) {
    Remove-Item -Path $Path -Force -ErrorAction SilentlyContinue
  }
  New-Item -ItemType File -Path $Path -Force | Out-Null
}

function Test-HttpReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url
  )

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  }
  catch {
    return $false
  }
}

function Get-ContainerStatus {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ContainerName
  )

  $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
  if ($null -eq $dockerCommand) {
    return "missing"
  }

  $status = Get-ContainerRuntimeStatus -ContainerName $ContainerName
  if ([string]::IsNullOrWhiteSpace($status)) {
    return "missing"
  }

  return $status
}

function Get-RecordedProcessState {
  if (-not (Test-Path $script:devProcessStateFile)) {
    return @()
  }

  try {
    $state = Get-Content -Path $script:devProcessStateFile -Raw | ConvertFrom-Json
  }
  catch {
    return @()
  }

  if ($null -eq $state.processes) {
    return @()
  }

  return @($state.processes)
}

function Test-DevEnvironmentRunning {
  $records = @(Get-RecordedProcessState)
  if ($records.Count -lt 3) {
    return $false
  }

  $requiredRoles = @("backend", "worker", "frontend")
  foreach ($role in $requiredRoles) {
    $record = $records | Where-Object { [string]$_.role -eq $role } | Select-Object -First 1
    if ($null -eq $record) {
      return $false
    }

    $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if ($null -eq $process) {
      return $false
    }
  }

  return $true
}

function Get-RoleHint {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Role
  )

  switch ($Role) {
    "backend" { return $script:backendUrl }
    "frontend" { return $script:frontendUrl }
    "worker" { return "celery background worker" }
    default { return "" }
  }
}

function Get-ProcessRuntimeStatus {
  param(
    [Parameter(Mandatory = $true)]
    [pscustomobject]$Record
  )

  $process = Get-Process -Id $Record.id -ErrorAction SilentlyContinue
  if ($null -eq $process) {
    return "stopped"
  }

  $role = [string]$Record.role
  if ($role -eq "backend" -and (Test-HttpReady -Url $script:backendUrl)) {
    return "ready"
  }
  if ($role -eq "frontend" -and (Test-HttpReady -Url $script:frontendUrl)) {
    return "ready"
  }
  return "running"
}

function Get-RecentLogText {
  param(
    [Parameter(Mandatory = $true)]
    [string]$StdOutPath,
    [Parameter(Mandatory = $true)]
    [string]$StdErrPath,
    [int]$MaxLines = 30
  )

  $lines = New-Object System.Collections.Generic.List[string]

  if (Test-Path $StdErrPath) {
    foreach ($line in (Get-Content -Path $StdErrPath -Tail $MaxLines -ErrorAction SilentlyContinue)) {
      if (-not [string]::IsNullOrWhiteSpace($line)) {
        [void]$lines.Add("ERR> $line")
      }
    }
  }

  if (Test-Path $StdOutPath) {
    foreach ($line in (Get-Content -Path $StdOutPath -Tail $MaxLines -ErrorAction SilentlyContinue)) {
      if (-not [string]::IsNullOrWhiteSpace($line)) {
        [void]$lines.Add("OUT> $line")
      }
    }
  }

  if ($lines.Count -eq 0) {
    return "No recent output."
  }

  return (($lines | Select-Object -Last $MaxLines) -join [Environment]::NewLine)
}

function Start-LauncherProcess {
  if ($script:launcherProcess -and -not $script:launcherProcess.HasExited) {
    return
  }

  if (Test-DevEnvironmentRunning) {
    $script:lastLauncherExitCode = 0
    return
  }

  Ensure-RuntimeDirectory
  if (Test-Path $script:monitorCloseFlagFile) {
    Remove-Item -Path $script:monitorCloseFlagFile -Force -ErrorAction SilentlyContinue
  }

  Reset-LogFile -Path $script:launcherOutLog
  Reset-LogFile -Path $script:launcherErrLog

  $script:lastLauncherExitCode = $null
  $script:launcherProcess = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @(
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      $script:startScriptPath,
      "-NoMonitor"
    ) `
    -WorkingDirectory $script:root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $script:launcherOutLog `
    -RedirectStandardError $script:launcherErrLog `
    -PassThru
}

function Start-StopperProcess {
  param(
    [switch]$CloseMonitor
  )

  if ($script:stopProcess -and -not $script:stopProcess.HasExited) {
    return
  }

  Ensure-RuntimeDirectory
  Reset-LogFile -Path $script:closerOutLog
  Reset-LogFile -Path $script:closerErrLog

  $arguments = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $script:stopScriptPath
  )
  if ($CloseMonitor) {
    $arguments += "-CloseMonitor"
  }

  $script:lastCloserExitCode = $null
  $script:stopProcess = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $arguments `
    -WorkingDirectory $script:root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $script:closerOutLog `
    -RedirectStandardError $script:closerErrLog `
    -PassThru
}

function Get-MonitorRows {
  $rows = @(
    [pscustomobject]@{
      Name = "postgres"
      Status = Get-ContainerStatus -ContainerName "spiderbilibili-postgres"
      Pid = "-"
      Hint = "docker compose"
    }
    [pscustomobject]@{
      Name = "redis"
      Status = Get-ContainerStatus -ContainerName "spiderbilibili-redis"
      Pid = "-"
      Hint = "docker compose"
    }
  )

  foreach ($record in (Get-RecordedProcessState)) {
    $rows += [pscustomobject]@{
      Name = [string]$record.role
      Status = Get-ProcessRuntimeStatus -Record $record
      Pid = [string]$record.id
      Hint = Get-RoleHint -Role ([string]$record.role)
    }
  }

  if ($script:launcherProcess) {
    $launcherStatus = "idle"
    if (-not $script:launcherProcess.HasExited) {
      $launcherStatus = "starting"
    }
    elseif ($null -ne $script:lastLauncherExitCode -and $script:lastLauncherExitCode -ne 0) {
      $launcherStatus = "failed"
    }
    elseif ($null -ne $script:lastLauncherExitCode) {
      $launcherStatus = "completed"
    }

    $rows += [pscustomobject]@{
      Name = "launcher"
      Status = $launcherStatus
      Pid = if ($script:launcherProcess.HasExited) { "-" } else { [string]$script:launcherProcess.Id }
      Hint = "startup orchestration"
    }
  }

  return $rows
}

function Set-StatusText {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Text
  )

  if ($script:lastStatusText -eq $Text) {
    return
  }

  $script:lastStatusText = $Text
  $statusLabel.Text = $Text
}

function Update-ProcessExitState {
  if ($script:launcherProcess -and $script:launcherProcess.HasExited -and $null -eq $script:lastLauncherExitCode) {
    $script:lastLauncherExitCode = $script:launcherProcess.ExitCode
  }

  if ($script:stopProcess -and $script:stopProcess.HasExited -and $null -eq $script:lastCloserExitCode) {
    $script:lastCloserExitCode = $script:stopProcess.ExitCode
  }
}

function Update-StatusGrid {
  $rows = @(Get-MonitorRows)
  $signature = ($rows | ConvertTo-Json -Compress)
  if ($script:lastStatusGridSignature -eq $signature) {
    return
  }

  $script:lastStatusGridSignature = $signature
  $statusList.BeginUpdate()
  $statusList.Items.Clear()
  foreach ($row in $rows) {
    $item = New-Object System.Windows.Forms.ListViewItem($row.Name)
    [void]$item.SubItems.Add($row.Status)
    [void]$item.SubItems.Add($row.Pid)
    [void]$item.SubItems.Add($row.Hint)
    [void]$statusList.Items.Add($item)
  }
  $statusList.EndUpdate()
}

function Set-LogBoxText {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Key,
    [Parameter(Mandatory = $true)]
    $TextBox,
    [Parameter(Mandatory = $true)]
    [string]$Value
  )

  if ($script:lastLogSnapshots.ContainsKey($Key) -and $script:lastLogSnapshots[$Key] -eq $Value) {
    return
  }

  $script:lastLogSnapshots[$Key] = $Value
  $TextBox.Text = $Value
}

function Update-LogTabs {
  Set-LogBoxText -Key "launcher" -TextBox $launcherLogBox -Value (Get-RecentLogText -StdOutPath $script:launcherOutLog -StdErrPath $script:launcherErrLog)
  Set-LogBoxText -Key "closer" -TextBox $closerLogBox -Value (Get-RecentLogText -StdOutPath $script:closerOutLog -StdErrPath $script:closerErrLog)

  $processRecords = @{}
  foreach ($record in (Get-RecordedProcessState)) {
    $processRecords[[string]$record.role] = $record
  }

  if ($processRecords.ContainsKey("backend")) {
    Set-LogBoxText -Key "backend" -TextBox $backendLogBox -Value (Get-RecentLogText -StdOutPath $processRecords["backend"].stdoutPath -StdErrPath $processRecords["backend"].stderrPath)
  }
  else {
    Set-LogBoxText -Key "backend" -TextBox $backendLogBox -Value "Backend is not running."
  }

  if ($processRecords.ContainsKey("worker")) {
    Set-LogBoxText -Key "worker" -TextBox $workerLogBox -Value (Get-RecentLogText -StdOutPath $processRecords["worker"].stdoutPath -StdErrPath $processRecords["worker"].stderrPath)
  }
  else {
    Set-LogBoxText -Key "worker" -TextBox $workerLogBox -Value "Worker is not running."
  }

  if ($processRecords.ContainsKey("frontend")) {
    Set-LogBoxText -Key "frontend" -TextBox $frontendLogBox -Value (Get-RecentLogText -StdOutPath $processRecords["frontend"].stdoutPath -StdErrPath $processRecords["frontend"].stderrPath)
  }
  else {
    Set-LogBoxText -Key "frontend" -TextBox $frontendLogBox -Value "Frontend is not running."
  }
}

function Update-MonitorView {
  Update-ProcessExitState
  Update-StatusGrid
  Update-LogTabs

  if ($script:launcherProcess -and -not $script:launcherProcess.HasExited) {
    Set-StatusText -Text "Starting..."
    return
  }

  if ($script:stopProcess -and -not $script:stopProcess.HasExited) {
    Set-StatusText -Text "Stopping..."
    return
  }

  if ($script:lastLauncherExitCode -ne $null) {
    if ($script:lastLauncherExitCode -eq 0) {
      Set-StatusText -Text "Running"
    }
    else {
      Set-StatusText -Text "Start failed"
    }
    return
  }

  if ($script:lastCloserExitCode -ne $null) {
    if ($script:lastCloserExitCode -eq 0) {
      Set-StatusText -Text "Stopped"
    }
    else {
      Set-StatusText -Text "Stop failed"
    }
    return
  }

  Set-StatusText -Text "Ready"
}

function New-LogTextBox {
  $textBox = New-Object System.Windows.Forms.TextBox
  $textBox.Multiline = $true
  $textBox.ReadOnly = $true
  $textBox.ScrollBars = "Vertical"
  $textBox.Dock = "Fill"
  $textBox.BackColor = [System.Drawing.Color]::FromArgb(15, 23, 42)
  $textBox.ForeColor = [System.Drawing.Color]::FromArgb(226, 232, 240)
  $textBox.Font = New-Object System.Drawing.Font("Consolas", 9)
  return $textBox
}

Ensure-RuntimeDirectory
if (Test-Path $script:monitorCloseFlagFile) {
  Remove-Item -Path $script:monitorCloseFlagFile -Force -ErrorAction SilentlyContinue
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "SpiderBilibili Monitor"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(1180, 780)
$form.MinimumSize = New-Object System.Drawing.Size(1040, 700)
$form.BackColor = [System.Drawing.Color]::FromArgb(241, 245, 249)

$rootLayout = New-Object System.Windows.Forms.TableLayoutPanel
$rootLayout.Dock = "Fill"
$rootLayout.RowCount = 3
$rootLayout.ColumnCount = 1
$rootLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 64)))
$rootLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))
$rootLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 28)))
$form.Controls.Add($rootLayout)

$headerLayout = New-Object System.Windows.Forms.TableLayoutPanel
$headerLayout.Dock = "Fill"
$headerLayout.ColumnCount = 2
$headerLayout.RowCount = 1
$headerLayout.BackColor = [System.Drawing.Color]::White
$headerLayout.Padding = New-Object System.Windows.Forms.Padding(18, 12, 18, 8)
$headerLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
$headerLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
$rootLayout.Controls.Add($headerLayout, 0, 0)

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "SpiderBilibili Monitor"
$titleLabel.AutoSize = $true
$titleLabel.Dock = "Fill"
$titleLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
$titleLabel.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 15, [System.Drawing.FontStyle]::Bold)
$titleLabel.ForeColor = [System.Drawing.Color]::FromArgb(15, 23, 42)
$headerLayout.Controls.Add($titleLabel, 0, 0)

$buttonPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$buttonPanel.FlowDirection = "LeftToRight"
$buttonPanel.WrapContents = $false
$buttonPanel.AutoSize = $true
$buttonPanel.Dock = "Fill"
$buttonPanel.Margin = New-Object System.Windows.Forms.Padding(0)
$headerLayout.Controls.Add($buttonPanel, 1, 0)

$startButton = New-Object System.Windows.Forms.Button
$startButton.Text = "Start"
$startButton.AutoSize = $true
$startButton.Margin = New-Object System.Windows.Forms.Padding(8, 4, 0, 0)
$startButton.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 5)
$buttonPanel.Controls.Add($startButton)

$stopButton = New-Object System.Windows.Forms.Button
$stopButton.Text = "Stop"
$stopButton.AutoSize = $true
$stopButton.Margin = New-Object System.Windows.Forms.Padding(8, 4, 0, 0)
$stopButton.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 5)
$buttonPanel.Controls.Add($stopButton)

$openFrontendButton = New-Object System.Windows.Forms.Button
$openFrontendButton.Text = "Frontend"
$openFrontendButton.AutoSize = $true
$openFrontendButton.Margin = New-Object System.Windows.Forms.Padding(8, 4, 0, 0)
$openFrontendButton.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 5)
$buttonPanel.Controls.Add($openFrontendButton)

$openLogsButton = New-Object System.Windows.Forms.Button
$openLogsButton.Text = "Logs"
$openLogsButton.AutoSize = $true
$openLogsButton.Margin = New-Object System.Windows.Forms.Padding(8, 4, 0, 0)
$openLogsButton.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 5)
$buttonPanel.Controls.Add($openLogsButton)

$closePanelButton = New-Object System.Windows.Forms.Button
$closePanelButton.Text = "Close"
$closePanelButton.AutoSize = $true
$closePanelButton.Margin = New-Object System.Windows.Forms.Padding(8, 4, 0, 0)
$closePanelButton.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 5)
$buttonPanel.Controls.Add($closePanelButton)

$contentSplit = New-Object System.Windows.Forms.SplitContainer
$contentSplit.Dock = "Fill"
$contentSplit.Orientation = "Vertical"
$contentSplit.SplitterDistance = 410
$contentSplit.BackColor = [System.Drawing.Color]::FromArgb(226, 232, 240)
$rootLayout.Controls.Add($contentSplit, 0, 1)

$leftPanel = New-Object System.Windows.Forms.Panel
$leftPanel.Dock = "Fill"
$leftPanel.Padding = New-Object System.Windows.Forms.Padding(16, 16, 8, 16)
$contentSplit.Panel1.Controls.Add($leftPanel)

$statusGroup = New-Object System.Windows.Forms.GroupBox
$statusGroup.Text = "Runtime Status"
$statusGroup.Dock = "Fill"
$statusGroup.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 10, [System.Drawing.FontStyle]::Bold)
$leftPanel.Controls.Add($statusGroup)

$statusList = New-Object System.Windows.Forms.ListView
$statusList.Dock = "Fill"
$statusList.View = "Details"
$statusList.FullRowSelect = $true
$statusList.GridLines = $true
$statusList.HideSelection = $false
$statusList.HeaderStyle = "Nonclickable"
[void]$statusList.Columns.Add("Component", 110)
[void]$statusList.Columns.Add("Status", 90)
[void]$statusList.Columns.Add("PID", 80)
[void]$statusList.Columns.Add("Hint", 220)
[System.Windows.Forms.ListView].GetProperty(
  "DoubleBuffered",
  [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic
).SetValue($statusList, $true, $null)
$statusGroup.Controls.Add($statusList)

$rightPanel = New-Object System.Windows.Forms.Panel
$rightPanel.Dock = "Fill"
$rightPanel.Padding = New-Object System.Windows.Forms.Padding(8, 16, 16, 16)
$contentSplit.Panel2.Controls.Add($rightPanel)

$logTabs = New-Object System.Windows.Forms.TabControl
$logTabs.Dock = "Fill"
$rightPanel.Controls.Add($logTabs)

$launcherTab = New-Object System.Windows.Forms.TabPage
$launcherTab.Text = "Launcher"
$launcherLogBox = New-LogTextBox
$launcherTab.Controls.Add($launcherLogBox)
[void]$logTabs.TabPages.Add($launcherTab)

$closerTab = New-Object System.Windows.Forms.TabPage
$closerTab.Text = "Closer"
$closerLogBox = New-LogTextBox
$closerTab.Controls.Add($closerLogBox)
[void]$logTabs.TabPages.Add($closerTab)

$backendTab = New-Object System.Windows.Forms.TabPage
$backendTab.Text = "Backend"
$backendLogBox = New-LogTextBox
$backendTab.Controls.Add($backendLogBox)
[void]$logTabs.TabPages.Add($backendTab)

$workerTab = New-Object System.Windows.Forms.TabPage
$workerTab.Text = "Worker"
$workerLogBox = New-LogTextBox
$workerTab.Controls.Add($workerLogBox)
[void]$logTabs.TabPages.Add($workerTab)

$frontendTab = New-Object System.Windows.Forms.TabPage
$frontendTab.Text = "Frontend"
$frontendLogBox = New-LogTextBox
$frontendTab.Controls.Add($frontendLogBox)
[void]$logTabs.TabPages.Add($frontendTab)

$statusBarPanel = New-Object System.Windows.Forms.Panel
$statusBarPanel.Dock = "Fill"
$statusBarPanel.Padding = New-Object System.Windows.Forms.Padding(14, 2, 14, 2)
$statusBarPanel.BackColor = [System.Drawing.Color]::White
$rootLayout.Controls.Add($statusBarPanel, 0, 2)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Dock = "Fill"
$statusLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
$statusLabel.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 8.5)
$statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(51, 65, 85)
$statusBarPanel.Controls.Add($statusLabel)

$startButton.Add_Click({
  Start-LauncherProcess
  Update-MonitorView
})

$stopButton.Add_Click({
  Start-StopperProcess
  Update-MonitorView
})

$openFrontendButton.Add_Click({
  Start-Process $script:frontendUrl | Out-Null
})

$openLogsButton.Add_Click({
  Ensure-RuntimeDirectory
  Start-Process explorer.exe $script:logDir | Out-Null
})

$closePanelButton.Add_Click({
  $form.Close()
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({
  if (Test-Path $script:monitorCloseFlagFile) {
    Remove-Item -Path $script:monitorCloseFlagFile -Force -ErrorAction SilentlyContinue
    $timer.Stop()
    $form.Close()
    return
  }

  Update-MonitorView
})

$form.Add_Shown({
  Update-MonitorView
  $timer.Start()
  if ($AutoStart) {
    Start-LauncherProcess
    Update-MonitorView
  }
})

$form.Add_FormClosed({
  $timer.Stop()
})

[void]$form.ShowDialog()
