Dim shell
Dim fso
Dim scriptDir
Dim monitorPath
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
monitorPath = fso.BuildPath(scriptDir, "dev-monitor.ps1")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -STA -File """ & monitorPath & """ -AutoStart"

shell.Run command, 0, False
