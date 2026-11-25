!macro customInstall
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\resources\cli-install.ps1" -Prepare'
  Pop $0
  StrCmp $0 "0" sami_cli_ready
    Abort "SAMI could not prepare its CLI. Open installer details for the error, then retry after fixing it."
  sami_cli_ready:
!macroend
