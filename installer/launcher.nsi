Unicode true
Target amd64-unicode
Name "VKV Documentcontrole"
OutFile "build/payload/VKV-Documentcontrole.exe"
RequestExecutionLevel user
SilentInstall silent
Section
  SetOutPath "$EXEDIR"
  ExecWait '"$EXEDIR\python\python.exe" "$EXEDIR\desktop.py"' $0
  IfErrors 0 +2
  MessageBox MB_ICONSTOP "VKV kon niet starten. Installeer de app opnieuw."
SectionEnd
