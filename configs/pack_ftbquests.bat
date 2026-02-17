@echo off
setlocal

REM Navigate to the configs directory (where this script is located)
cd /d "%~dp0"

REM Delete existing ftbquests.zip if it exists
if exist "ftbquests.zip" (
    echo Deleting existing ftbquests.zip...
    del /f "ftbquests.zip"
)

REM Compress ftbquests folder into ftbquests.zip using 7-Zip
echo Compressing ftbquests folder into ftbquests.zip...
"C:\Program Files\7-Zip\7z.exe" a -tzip -mtc=off ftbquests.zip ftbquests

REM Check if compression was successful
if not exist "ftbquests.zip" (
    echo ERROR: Failed to create ftbquests.zip
    exit /b 1
)

REM Calculate and display file size and MD5 hash
echo.
echo File size (bytes):
powershell -NoProfile -Command "(Get-Item 'ftbquests.zip').Length"
echo.
echo MD5 Hash of ftbquests.zip:
powershell -NoProfile -Command "(Get-FileHash -Path 'ftbquests.zip' -Algorithm MD5).Hash"

endlocal

pause
