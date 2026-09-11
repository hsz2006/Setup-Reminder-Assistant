param([switch]$CleanLegacy)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$launcher = Join-Path $projectRoot '启动助手.vbs'
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Launcher missing.' }
$pythonPath = (Get-Content -LiteralPath (Join-Path $projectRoot 'config\python-path.txt') -Raw).Trim()
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Conda Python missing. Check config/python-path.txt.' }
if (-not (Test-Path -LiteralPath (Join-Path (Split-Path $pythonPath) 'pythonw.exe'))) { throw 'Conda pythonw.exe missing.' }
$startupDirectory = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupDirectory 'StudyStartAssistant.lnk'
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$shortcut.Arguments = '"' + $launcher + '" --background'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Output 'New login startup registered.'
$desktopDirectory = [Environment]::GetFolderPath('Desktop')
$desktopShortcut = $shellObject.CreateShortcut((Join-Path $desktopDirectory '启动提醒助手.lnk'))
$desktopShortcut.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$desktopShortcut.Arguments = '"' + $launcher + '"'
$desktopShortcut.WorkingDirectory = $projectRoot
$desktopShortcut.WindowStyle = 7
$iconFile = Join-Path $projectRoot 'assets\app.ico'
if (Test-Path -LiteralPath $iconFile) {
    $desktopShortcut.IconLocation = $iconFile
    $shortcut.IconLocation = $iconFile
    $shortcut.Save()
}
$desktopShortcut.Save()
Write-Output 'Desktop shortcut created.'
if ($CleanLegacy) {
    $legacyPath = 'C:\Users\lenovo\StudyReminder'
    $tasks = @(Get-ScheduledTask | Where-Object { $_.TaskName -like 'StudyReminder*' })
    foreach ($task in $tasks) {
        $actionText = ($task.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }) -join ' '
        if ($actionText -notlike '*StudyReminder*') { throw ('Unexpected action; not removed: ' + $task.TaskName) }
        Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false
        Write-Output ('Removed old task: ' + $task.TaskName)
    }
    if (Test-Path -LiteralPath $legacyPath) {
        $resolvedLegacy = (Resolve-Path -LiteralPath $legacyPath).ProviderPath.TrimEnd('\')
        if ($resolvedLegacy -cne 'C:\Users\lenovo\StudyReminder') { throw 'Unexpected legacy directory.' }
        if ((Get-Item -LiteralPath $legacyPath).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Legacy directory is a reparse point.' }
        Remove-Item -LiteralPath $resolvedLegacy -Recurse -Force
        Write-Output 'Removed old runtime directory.'
    }
}
