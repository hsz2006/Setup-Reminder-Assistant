Option Explicit
Dim shell, fso, folder, python, mode, config
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
Set config = fso.OpenTextFile(folder & "\config\python-path.txt", 1)
python = fso.BuildPath(fso.GetParentFolderName(Trim(config.ReadLine)), "pythonw.exe")
config.Close
If Not fso.FileExists(python) Then
    MsgBox "Conda Python missing. Check config\python-path.txt", 16, "Startup assistant"
    WScript.Quit 1
End If
mode = ""
If WScript.Arguments.Count > 0 Then mode = " --background"
shell.Run """" & python & """ """ & folder & "\app.py""" & mode, 1, False
