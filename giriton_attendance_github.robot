*** Settings ***
Resource    resources/keywords_github.robot
Resource    resources/variables.robot
Library    resources/raw_giriton_export_sheet.py
Library    resources/giriton_attendance_scraper.py
Library    SeleniumLibrary
Library    DateTime
Library    Collections


*** Variables ***
${RUN_START_DATE}


*** Test Cases ***
Giriton Attendance Github
    keywords_github.Bejelentkezes
    keywords_github.Click Attendance
    Sleep    5s

    ${today}=    Get Current Date
    ...    result_format=%Y-%m-%d

    ${base_date}=    Set Variable    ${today}

    IF    '${RUN_START_DATE}' != ''
        ${base_date}=    Set Variable    ${RUN_START_DATE}
    END

    ${attendance_datum_giriton}=    Add Time To Date
    ...    ${base_date}
    ...    0 days
    ...    result_format=%d/%m/%Y

    ${attendance_datum_sheet}=    Add Time To Date
    ...    ${base_date}
    ...    0 days
    ...    result_format=%Y-%m-%d

    Log To Console
    ...    ATTENDANCE_DATUM=${attendance_datum_giriton}

    Execute Javascript
    ...    const input=[...document.querySelectorAll('input.v-datefield-textfield')].find(el => el.offsetWidth > 0 && el.offsetHeight > 0); if(!input){throw new Error('Visible date input not found');} input.focus(); input.value=arguments[0]; input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true})); input.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
    ...    ARGUMENTS
    ...    ${attendance_datum_giriton}

    Sleep    5s

    ${attendance_rows}=    giriton_attendance_scraper.Scrape Attendance Rows
    ...    ${attendance_datum_sheet}

    ${attendance_count}=    Get Length    ${attendance_rows}

    Log To Console
    ...    ATTENDANCE_SOROK_SZAMA=${attendance_count}

    ${attendance_result}=    raw_giriton_export_sheet.Write Attendance Export
    ...    ${attendance_rows}

    Log To Console
    ...    ATTENDANCE_EXPORT=${attendance_result}

    ${stats_result}=    raw_giriton_export_sheet.Build Courier Login Stats

    Log To Console
    ...    COURIER_LOGIN_STATS=${stats_result}
