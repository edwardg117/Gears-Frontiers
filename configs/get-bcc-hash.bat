@echo off
setlocal

REM Navigate to the configs directory (where this script is located)
cd /d "%~dp0"

REM Calculate and display file size and MD5 hash
echo.
echo File size (bytes):
powershell -NoProfile -Command "(Get-Item 'bcc-common.toml').Length"
echo.
echo MD5 Hash of ftbquests.zip:
powershell -NoProfile -Command "(Get-FileHash -Path 'bcc-common.toml' -Algorithm MD5).Hash"

endlocal

pause
