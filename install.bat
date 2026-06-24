@echo off
echo Giriton dashboard kornyezet telepitese...

REM Virtual environment letrehozasa
python -m venv venv

REM Virtual environment aktivalasa
call venv\Scripts\activate.bat

REM Pip frissites
python -m pip install --upgrade pip

REM Streamlit app fuggosegek
pip install -r requirements.txt

REM Robot Framework / Selenium teszt fuggosegek
pip install robotframework
pip install robotframework-seleniumlibrary
pip install selenium
pip install robotframework-requests
pip install openpyxl
pip install gspread
pip install google-auth
pip install webdriver-manager
pip install robotframework-jsonlibrary
pip install robotframework-datadriver

echo.
echo Telepites kesz.
pause
