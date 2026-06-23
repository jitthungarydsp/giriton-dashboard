@echo off
echo Robot Framework kornyezet telepitese...

REM Virtual environment letrehozasa
python -m venv venv

REM Virtual environment aktivalasa
call venv\Scripts\activate.bat

REM Pip frissites
python -m pip install --upgrade pip

REM Robot Framework
pip install robotframework

REM Selenium
pip install robotframework-seleniumlibrary
pip install selenium

REM Requests
pip install robotframework-requests

REM Excel kezeles
pip install openpyxl
pip install pandas

REM WebDriver manager
pip install webdriver-manager

REM Hasznos Robot libraryk
pip install robotframework-jsonlibrary
pip install robotframework-datadriver

echo.
echo Telepites kesz.
pause