@echo off
setlocal

if defined HERDR1_BASH goto run

set "HERDR1_BASH=%ProgramFiles%\Git\bin\bash.exe"
if exist "%HERDR1_BASH%" goto run

set "HERDR1_BASH=%LocalAppData%\Programs\Git\bin\bash.exe"
if exist "%HERDR1_BASH%" goto run

echo herdr1: Git Bash was not found. Set HERDR1_BASH to bash.exe. 1>&2
exit /b 127

:run
"%HERDR1_BASH%" --noprofile --norc -c "exec \"$HOME/.local/bin/herdr1\" \"$@\"" herdr1 %*
exit /b %ERRORLEVEL%
