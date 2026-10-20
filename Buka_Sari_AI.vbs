' Peluncur Harmoni Agent.
' PENTING: alamat TIDAK ditulis tetap. Berkas ini mencari letaknya sendiri,
' sehingga tetap benar walau foldernya dipindah atau dipasang di komputer lain.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
akar = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = akar

pywBawaan = akar & "\runtime\python\pythonw.exe"
If fso.FileExists(pywBawaan) Then
    sh.Run """" & pywBawaan & """ """ & akar & "\app_desktop.py""", 0, False
Else
    sh.Run "pyw """ & akar & "\app_desktop.py""", 0, False
End If
