@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "ROBOT_PYTHON=%~dp0.robot-venv\Scripts\python.exe"
if not exist "%ROBOT_PYTHON%" (
 echo Hianyzik a robot Python-kornyezete: .robot-venv
 echo A telepiteshez ne a Microsoft Store python aliast hasznald.
 pause
 exit /b 1
)
if /i "%~1"=="login" (
 "%ROBOT_PYTHON%" -u scripts\run_quality_form_worker.py --login
 goto done
)
if /i "%~1"=="check-login" (
 "%ROBOT_PYTHON%" -u scripts\run_quality_form_worker.py --check
 goto done
)
if /i "%~1"=="check" (
 "%ROBOT_PYTHON%" -u scripts\run_route_delay_submission_worker.py --check
 goto done
)
echo Google reklamacio-bekuldo robot indul.
echo A devtestben sorba allitott reklamaciokat tenylegesen BEKULDI.
echo Leallitas: Ctrl+C. Hagyd nyitva az ablakot.
"%ROBOT_PYTHON%" -u scripts\run_route_delay_submission_worker.py --watch
:done
if /i "%~1"=="check" exit /b %ERRORLEVEL%
pause
