Unicode true
Target amd64-unicode
!include "MUI2.nsh"
!include "x64.nsh"
Name "VKV Documentcontrole"
OutFile "dist/VKV-Documentcontrole-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\VKV Documentcontrole"
RequestExecutionLevel user
SetCompressor zlib
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Dutch"
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Deze versie vereist Windows 10/11 (64-bit)."
    Abort
  ${EndIf}
FunctionEnd
Section
  SetOutPath "$INSTDIR"
  File /r "build/payload/*"
  CreateDirectory "$SMPROGRAMS\VKV Documentcontrole"
  CreateShortcut "$SMPROGRAMS\VKV Documentcontrole\VKV Documentcontrole.lnk" "$INSTDIR\VKV-Documentcontrole.exe"
  CreateShortcut "$DESKTOP\VKV Documentcontrole.lnk" "$INSTDIR\VKV-Documentcontrole.exe"
  WriteUninstaller "$INSTDIR\Verwijderen.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VKV-mag" "DisplayName" "VKV Documentcontrole"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VKV-mag" "UninstallString" '"$INSTDIR\Verwijderen.exe"'
SectionEnd
Section "Uninstall"
  Delete "$DESKTOP\VKV Documentcontrole.lnk"
  RMDir /r "$SMPROGRAMS\VKV Documentcontrole"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VKV-mag"
SectionEnd
