*** Settings ***
Resource    resources/keywords_github.robot
Resource    resources/variables.robot
Resource    resources/giriton_shift_scraper.robot
Library    resources/googlesheet_modified_template.py
Library    SeleniumLibrary
Library    DateTime
Library    Collections
Library    String


*** Test Cases ***
Muszakok Figyelese

    keywords_github.Bejelentkezes

    keywords_github.Click Shift Subs

    Sleep    10

    ${today}=    Get Current Date
    ...    result_format=%Y-%m-%d

    @{rows}=    Create List

    FOR    ${nap}    IN RANGE    0    3

        ${datum_giriton}=    Add Time To Date
        ...    ${today}
        ...    ${nap} days
        ...    result_format=%d/%m/%Y

        ${datum_sheet}=    Add Time To Date
        ...    ${today}
        ...    ${nap} days
        ...    result_format=%Y-%m-%d

        Log To Console
        ...    DATUM=${datum_giriton}

        Click Element
        ...    xpath=//input[contains(@class,'v-datefield-textfield')]

        Press Keys
        ...    xpath=//input[contains(@class,'v-datefield-textfield')]
        ...    CTRL+A

        Input Text
        ...    xpath=//input[contains(@class,'v-datefield-textfield')]
        ...    ${datum_giriton}

        Press Keys
        ...    xpath=//input[contains(@class,'v-datefield-textfield')]
        ...    ENTER

        Sleep    3

        FOR    ${i}    IN RANGE    15

            Execute Javascript
            ...    let els=[...document.querySelectorAll('*')];
            ...    let scrollable=els.filter(e=>e.scrollHeight>e.clientHeight);
            ...    let biggest=scrollable.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0];
            ...    if(biggest){biggest.scrollTop=biggest.scrollHeight;}

            Sleep    1s

        END

        Sleep    2s

        Collect Visible Giriton Shift Rows
        ...    ${rows}
        ...    ${datum_sheet}

    END

    ${dbrows}=    Get Length    ${rows}

    Log To Console
    ...    SOROK_SZAMA=${dbrows}

    ${result}=    googlesheet_modified_template.Write All Shifts
    ...    ${rows}

    Log To Console
    ...    GOOGLE=${result}
