' Silent Background Launcher for GPF Smart Investor AI
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strCurrentDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strCurrentDir
' Run python run.py invisibly (0 = hide window, False = don't wait)
WshShell.Run """" & strCurrentDir & "\.venv\Scripts\python.exe"" run.py", 0, False
