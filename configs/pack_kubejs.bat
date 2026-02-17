@echo off
setlocal

REM Navigate to the configs directory (where this script is located)
cd /d "%~dp0"

REM Delete existing kubejs.zip if it exists
if exist "kubejs.zip" (
    echo Deleting existing kubejs.zip...
    del /f "kubejs.zip"
)

REM Compress kubejs folder into kubejs.zip using 7-Zip
echo Compressing kubejs folder into kubejs.zip...
"C:\Program Files\7-Zip\7z.exe" a -tzip -mtc=off kubejs.zip kubejs

REM Check if compression was successful
if not exist "kubejs.zip" (
    echo ERROR: Failed to create kubejs.zip
    exit /b 1
)

REM Calculate and display file size and MD5 hash
echo.
echo File size (bytes):
powershell -NoProfile -Command "(Get-Item 'kubejs.zip').Length"
echo.
echo MD5 Hash of kubejs.zip:
powershell -NoProfile -Command "(Get-FileHash -Path 'kubejs.zip' -Algorithm MD5).Hash"

endlocal

pause
