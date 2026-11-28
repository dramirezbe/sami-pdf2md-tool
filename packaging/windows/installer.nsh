!macro customHeader
  ShowInstDetails show
!macroend

!macro customInstall
  DetailPrint "Preparing SAMI CLI. Installation log: $LOCALAPPDATA\SAMI\installer.log"
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\resources\install-logged.ps1" -Helper "$INSTDIR\resources\cli-install.ps1"'
  Pop $0
  StrCmp $0 "0" sami_cli_ready
    SetErrorLevel 1
    IfSilent sami_install_abort
    MessageBox MB_OK|MB_ICONSTOP "SAMI could not prepare its CLI (code $0). See $LOCALAPPDATA\SAMI\installer.log for details."
  sami_install_abort:
    Abort
  sami_cli_ready:
!macroend
