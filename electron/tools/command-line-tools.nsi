; Windows installer for the OpenMS command line tools an app was built with
; (electron/scripts/package-tools.sh). Installs for the current user, without
; admin rights, and puts the tools on the user's PATH.
;
;   makensis -DAPP_NAME=<name> -DSRC=<folder with bin/ and share/>
;            -DOUT=<installer.exe> -DLABEL=<what was built> command-line-tools.nsi

Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user
ManifestDPIAware true

!ifndef APP_NAME | SRC | OUT
  !error "APP_NAME, SRC and OUT must be defined"
!endif
!ifndef LABEL
  !define LABEL "OpenMS"
!endif

!define PRODUCT "${APP_NAME} command line tools"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}-command-line-tools"

Name "${PRODUCT}"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}-command-line-tools"
InstallDirRegKey HKCU "${UNINST_KEY}" "InstallLocation"

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "${PRODUCT}"
!define MUI_WELCOMEPAGE_TEXT "This installs the OpenMS command line tools ${APP_NAME} runs (${LABEL}) for your user account.$\r$\n$\r$\nTheir folder is added to your PATH, so a new command prompt can run them by name, for example FLASHDeconv -help."
!define MUI_FINISHPAGE_TEXT "The tools are in $INSTDIR\bin. Open a new command prompt (or the ${PRODUCT} entry in the Start menu) to use them."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; Adds or removes $INSTDIR\bin in the user's PATH. .NET's SetEnvironmentVariable
; also tells running programs (Explorer) that the environment changed. The folder
; reaches PowerShell as an environment variable, so a quote in it cannot break
; the command.
!macro EditUserPath ACTION
  System::Call 'Kernel32::SetEnvironmentVariable(t "OPENMS_TOOLS_BIN", t "$INSTDIR\bin")'
  nsExec::ExecToLog `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$d=$$env:OPENMS_TOOLS_BIN; $$p=[Environment]::GetEnvironmentVariable('Path','User'); if ($$p -eq $$null) { $$p='' }; $$parts=@($$p.Split(';') | Where-Object { $$_ -ne '' -and $$_ -ne $$d }); if ('${ACTION}' -eq 'add') { $$parts += $$d }; [Environment]::SetEnvironmentVariable('Path', ($$parts -join ';'), 'User')"`
  Pop $0
!macroend

Section "Command line tools" SecTools
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  !insertmacro EditUserPath add

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${PRODUCT}.lnk" "$SYSDIR\cmd.exe" \
    `/K "set PATH=$INSTDIR\bin;%PATH%&& cd /d %USERPROFILE%&& echo ${PRODUCT} (${LABEL}). Run a tool with -help to see its options."` \
    "$SYSDIR\cmd.exe" 0
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall ${PRODUCT}.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${PRODUCT}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${LABEL}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "OpenMS"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  !insertmacro EditUserPath remove
  Delete "$SMPROGRAMS\${APP_NAME}\${PRODUCT}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Uninstall ${PRODUCT}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  RMDir /r "$INSTDIR\bin"
  RMDir /r "$INSTDIR\share"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
