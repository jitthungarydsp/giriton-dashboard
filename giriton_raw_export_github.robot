*** Settings ***
Resource    resources/keywords_github.robot
Resource    resources/variables.robot
Library    resources/raw_giriton_export_sheet.py
Library    SeleniumLibrary
Library    DateTime
Library    Collections
Library    String


*** Variables ***
${RUN_START_DATE}
${DAYS_TO_SYNC}    10


*** Test Cases ***
Giriton Raw Export Github
    keywords_github.Bejelentkezes
    keywords_github.Click Shift Subs
    keywords_github.Select All Departments

    Sleep    10

    ${today}=    Get Current Date
    ...    result_format=%Y-%m-%d

    ${base_date}=    Set Variable    ${today}

    IF    '${RUN_START_DATE}' != ''
        ${base_date}=    Set Variable    ${RUN_START_DATE}
    END

    @{rows}=    Create List
    ${days_to_sync}=    Set Variable If    '${DAYS_TO_SYNC}' == ''    10    ${DAYS_TO_SYNC}
    ${days_to_sync}=    Convert To Integer    ${days_to_sync}

    FOR    ${nap}    IN RANGE    0    ${days_to_sync}
        ${datum_giriton}=    Add Time To Date
        ...    ${base_date}
        ...    ${nap} days
        ...    result_format=%d/%m/%Y

        ${datum_sheet}=    Add Time To Date
        ...    ${base_date}
        ...    ${nap} days
        ...    result_format=%Y-%m-%d

        ${datum_oldal}=    Add Time To Date
        ...    ${base_date}
        ...    ${nap} days
        ...    result_format=%d.%m.%Y

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

        Wait Until Giriton Date Is Loaded
        ...    ${datum_oldal}

        Execute Javascript
        ...    let els=[...document.querySelectorAll('*')]; let scrollable=els.filter(e=>e.scrollHeight>e.clientHeight); let biggest=scrollable.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0]; if(biggest){biggest.scrollTop=0;}

        Sleep    2

        FOR    ${i}    IN RANGE    15
            Execute Javascript
            ...    let els=[...document.querySelectorAll('*')];
            ...    let scrollable=els.filter(e=>e.scrollHeight>e.clientHeight);
            ...    let biggest=scrollable.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0];
            ...    if(biggest){biggest.scrollTop=biggest.scrollHeight;}

            Sleep    1s
        END

        Sleep    2s

        ${muszakok}=    Get WebElements
        ...    xpath=//div[contains(@class,'panel-title')]

        ${raktarak}=    Get WebElements
        ...    xpath=//div[contains(@class,'elementDirectionRtl ')]

        ${users}=    Get WebElements
        ...    xpath=//div[contains(@class,'subscribed-persons-label')]

        ${foglaltsagok}=    Get WebElements
        ...    xpath=//div[@class='v-label v-widget v-label-undef-w']

        @{uj_foglaltsagok}=    Create List

        ${dbfog}=    Get Length    ${foglaltsagok}

        FOR    ${i}    IN RANGE    ${dbfog}
            ${txt}=    Get Text    ${foglaltsagok}[${i}]
            ${txt}=    Strip String    ${txt}

            IF    '/' in '${txt}'
                Append To List
                ...    ${uj_foglaltsagok}
                ...    ${foglaltsagok}[${i}]
            END
        END

        ${foglaltsagok}=    Set Variable    ${uj_foglaltsagok}
        ${db}=    Get Length    ${muszakok}

        FOR    ${i}    IN RANGE    ${db}
            ${muszak}=        Get Text    ${muszakok}[${i}]
            ${raktar_txt}=    Get Text    ${raktarak}[${i}]
            ${user_txt}=      Get Text    ${users}[${i}]
            ${foglaltsag}=    Get Text    ${foglaltsagok}[${i}]
            ${foglaltsag}=    Strip String    ${foglaltsag}

            ${fog_parts}=    Split String
            ...    ${foglaltsag}
            ...    /

            ${foglalt}=    Strip String
            ...    ${fog_parts}[0]
            IF    '(' in '''${foglalt}'''
                ${foglalt}=    Fetch From Left    ${foglalt}    (
                ${foglalt}=    Strip String    ${foglalt}
            END

            ${maximum}=    Strip String
            ...    ${fog_parts}[1]
            IF    '(' in '''${maximum}'''
                ${maximum}=    Fetch From Left    ${maximum}    (
                ${maximum}=    Strip String    ${maximum}
            END

            ${foglalt_int}=    Convert To Integer    ${foglalt}
            ${maximum_int}=    Convert To Integer    ${maximum}

            ${parts}=       Split String    ${muszak}    körös:
            ${idoszak}=     Set Variable    ${parts}[1]
            ${idoszak}=     Strip String    ${idoszak}
            ${times}=       Split String    ${idoszak}    -

            ${kezdes}=      Strip String    ${times}[0]
            ${ora}=         Fetch From Left    ${kezdes}    :
            ${perc}=        Fetch From Right   ${kezdes}    :
            ${ora}=         Convert To Integer    ${ora}
            ${kezdes}=      Set Variable    ${ora}:${perc}

            ${vege}=        Strip String    ${times}[1]
            ${ora}=         Fetch From Left    ${vege}    :
            ${perc}=        Fetch From Right   ${vege}    :
            ${ora}=         Convert To Integer    ${ora}
            ${vege}=        Set Variable    ${ora}:${perc}

            ${nev_parts}=    Split String    ${user_txt}    :
            ${nev}=          Set Variable    ${nev_parts}[1]
            ${nev}=          Strip String    ${nev}

            IF    '${nev}' == '(none)'
                @{nevek}=    Create List    URES
            ELSE
                @{nevek}=    Split String    ${nev}    ,
            END

            ${raktar}=    Set Variable    URES

            IF    'BUD1' in '''${raktar_txt}'''
                ${raktar}=    Set Variable    BUD1
            ELSE IF    'BUD2' in '''${raktar_txt}'''
                ${raktar}=    Set Variable    BUD2
            END

            FOR    ${egy_nev}    IN    @{nevek}
                ${egy_nev}=    Strip String    ${egy_nev}

                ${row}=    Create List
                ...    ${datum_sheet}
                ...    ${kezdes}
                ...    ${vege}
                ...    ${raktar}
                ...    ${foglaltsag}
                ...    ${foglalt}
                ...    ${maximum}
                ...    ${egy_nev}

                Append To List
                ...    ${rows}
                ...    ${row}
            END
        END
    END

    ${dbrows}=    Get Length    ${rows}

    Log To Console
    ...    SOROK_SZAMA=${dbrows}

    ${result}=    raw_giriton_export_sheet.Write Raw Export
    ...    ${rows}

    Log To Console
    ...    RAW_EXPORT=${result}


*** Keywords ***
Wait Until Giriton Date Is Loaded
    [Arguments]    ${datum_oldal}
    Wait Until Keyword Succeeds
    ...    30x
    ...    1s
    ...    Giriton Visible Date Should Be
    ...    ${datum_oldal}
    Wait Until Keyword Succeeds
    ...    30x
    ...    1s
    ...    Giriton Loading Should Be Finished
    Wait Until Page Contains Element
    ...    xpath=//div[contains(@class,'panel-title')]
    ...    timeout=30s
    Sleep    2s


Giriton Visible Date Should Be
    [Arguments]    ${datum_oldal}
    ${visible_text}=    Execute Javascript
    ...    return document.body ? document.body.innerText : '';
    Should Contain
    ...    ${visible_text}
    ...    ${datum_oldal}


Giriton Loading Should Be Finished
    ${is_loading}=    Execute Javascript
    ...    return [...document.querySelectorAll('.v-loading-indicator, .v-loading-indicator-delay, .v-loading-indicator-wait')].some(el => { const style = window.getComputedStyle(el); return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'; });
    Should Be Equal
    ...    ${is_loading}
    ...    ${False}
