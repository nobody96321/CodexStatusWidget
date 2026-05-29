Option Explicit

Dim shell, fso, scriptDir, exePath, srcPath, args, i, launcher, command, env, oldPythonPath

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = fso.BuildPath(scriptDir, "CodexStatusWidget.exe")
srcPath = fso.BuildPath(scriptDir, "src")
args = ""

For i = 0 To WScript.Arguments.Count - 1
  args = args & " " & Quote(WScript.Arguments(i))
Next

shell.CurrentDirectory = scriptDir
Set env = shell.Environment("PROCESS")
oldPythonPath = env("PYTHONPATH")
If oldPythonPath <> "" Then
  env("PYTHONPATH") = srcPath & ";" & oldPythonPath
Else
  env("PYTHONPATH") = srcPath
End If

If fso.FileExists(exePath) Then
  command = Quote(exePath) & args
Else
  launcher = ResolveCommand(shell, "pyw.exe")
  If launcher <> "" Then
    command = Quote(launcher) & " -3 -m codex_status_widget" & args
  Else
    launcher = ResolveCommand(shell, "pythonw.exe")
    If launcher <> "" Then
      command = Quote(launcher) & " -m codex_status_widget" & args
    Else
      launcher = ResolveCommand(shell, "py.exe")
      If launcher <> "" Then
        command = Quote(launcher) & " -3 -m codex_status_widget" & args
      Else
        command = "python -m codex_status_widget" & args
      End If
    End If
  End If
End If

shell.Run command, 0, False

Function Quote(value)
  Quote = """" & Replace(CStr(value), """", """""") & """"
End Function

Function ResolveCommand(shellObj, name)
  On Error Resume Next

  Dim exec, line
  Set exec = shellObj.Exec("cmd /c where " & name)
  If Err.Number <> 0 Then
    Err.Clear
    ResolveCommand = ""
    Exit Function
  End If

  line = exec.StdOut.ReadLine
  If Err.Number <> 0 Then
    Err.Clear
    ResolveCommand = ""
  Else
    ResolveCommand = Trim(line)
  End If

  On Error GoTo 0
End Function
