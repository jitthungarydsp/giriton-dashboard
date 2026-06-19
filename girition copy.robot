*** Settings ***
Resource    ../robots/resource/keywords.robot
Resource    ../robots/resource/variables.robot
Library    googlesheet.py
Library    SeleniumLibrary
Library    DateTime
Library    Collections
Library    String


*** Variables ***
${START_DATE}    05/06/2026
${END_DATE}      12/06/2026



*** Test Cases ***
Muszakok Figyelese

    Bejelentkezes

    keywords.Click Shift Subs

    @{rows}=    Create List

    ${today}=    Get Current Date
    ...    result_format=%Y-%m-%d

    FOR    ${nap}    IN RANGE    0    3

        ${datum}=    Add Time To Date
        ...    ${today}
        ...    ${nap} days
        ...    result_format=%d/%m/%Y

        Log To Console
        ...    DATUM=${datum}

        Beallit Datum
        ...    ${datum}

        ${napi_rows}=    Muszakok Kiolvasasa
        ...    ${datum}

        Extend List
        ...    ${rows}
        ...    ${napi_rows}

    END

    ${dbrows}=    Get Length
    ...    ${rows}

    Log To Console
    ...    SOROK_SZAMA=${dbrows}

    ${result}=    Write All Shifts
    ...    ${rows}

    Log To Console
    ...    GOOGLE=${result}