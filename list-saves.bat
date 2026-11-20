@echo off
setlocal DisableDelayedExpansion
if "%~1"=="" goto usage
py -3 "%~dp0kh2save.py" list "%~1"
if errorlevel 1 goto end
echo.
echo To import, open Command Prompt and adapt this command:
echo py -3 "%~dp0kh2save.py" convert "%~1" --source 1 --into "C:\path\to\KHIIFM_WW.png" --slot 2
goto end
:usage
echo Drag your PCSX2 memory card file or card folder onto this batch file.
:end
pause
