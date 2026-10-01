' Silent Background Launcher for GPF Smart Investor AI
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strCurrentDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strCurrentDir
q = Chr(34)
cmd = q & strCurrentDir & "\.venv\Scripts\pythonw.exe" & q & " " & q & strCurrentDir & "\start_bot.py" & q
WshShell.Run cmd, 0, False

