@echo off
setlocal DisableDelayedExpansion
title law_summary
pushd "%~dp0"
if errorlevel 1 goto folder_error
set "PYTHONHOME="
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%~dp0vendor\cp313;%~dp0vendor\common;%~dp0"
if not exist "%~dp0runtime\python\python.exe" goto runtime_error
echo law_summary - using the included Python runtime.
echo No installation or package download is needed.
"%~dp0runtime\python\python.exe" -S "%~dp0start_web.py" %*
set "LAW_SUMMARY_EXIT=%ERRORLEVEL%"
popd
if not "%LAW_SUMMARY_EXIT%"=="0" (
  echo.
  echo law_summary could not start. See law_summary_startup.log.
  pause
)
exit /b %LAW_SUMMARY_EXIT%
:runtime_error
echo Bundled Python is missing. Extract the entire ZIP before running this file.
popd
pause
exit /b 1
:folder_error
echo Cannot open the law_summary folder. Extract the entire ZIP to a writable folder.
pause
exit /b 1
