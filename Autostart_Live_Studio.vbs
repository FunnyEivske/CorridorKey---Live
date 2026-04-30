Set WshShell = CreateObject("WScript.Shell")
' 0 betyr "skjul vindu" (hidden window)
WshShell.Run "cmd.exe /c uv run --extra live --extra cuda live_studio.py --autostart", 0
Set WshShell = Nothing
