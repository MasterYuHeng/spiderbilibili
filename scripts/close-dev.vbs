Dim shell
Dim fso
Dim scriptDir
Dim stopScriptPath
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
stopScriptPath = fso.BuildPath(scriptDir, "stop-dev.ps1")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & stopScriptPath & """ -CloseMonitor"

shell.Run command, 0, False
