' Harmoni Agent Startup - Background Service Launcher
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

harmoniDir = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\HarmoniAgent")
pywExe = harmoniDir & "\runtime\python\pythonw.exe"
servicePy = harmoniDir & "\service_background.py"

If fso.FileExists(pywExe) And fso.FileExists(servicePy) Then
    WshShell.CurrentDirectory = harmoniDir
    WshShell.Run """" & pywExe & """ """ & servicePy & """", 0, False
End If
