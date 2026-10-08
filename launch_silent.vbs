Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

cmd = "pythonw """ & scriptDir & "\app\main.py"" --startup"
WshShell.Run cmd, 0, False
