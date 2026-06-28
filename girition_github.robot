*** Settings ***
Resource    resources/keywords_github.robot
Resource    resources/variables.robot
Library    resources/googlesheet_modified_template.py
Library    SeleniumLibrary
Library    DateTime
Library    Collections
Library    String


*** Variables ***
${START_DATE}    05/06/2026
${END_DATE}      12/06/2026



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

            ${foglaltsag}=    Get Text    ${foglaltsagok}[${i}]
            ${foglaltsag}=    Strip String    ${foglaltsag}

            ${fog_parts}=    Split String
            ...    ${foglaltsag}
            ...    /

            ${foglalt}=    Strip String
            ...    ${fog_parts}[0]

            ${maximum}=    Strip String
            ...    ${fog_parts}[1]

            ${foglalt_int}=    Convert To Integer    ${foglalt}
            ${maximum_int}=    Convert To Integer    ${maximum}

            ${szabad}=    Evaluate
            ...    ${maximum_int}-${foglalt_int}

            ${parts}=       Split String    ${muszak}    körös:
            ${idoszak}=     Set Variable    ${parts}[1]
            ${idoszak}=     Strip String    ${idoszak}

            ${times}=       Split String    ${idoszak}    -

            ${kezdes}=      Strip String    ${times}[0]
            ${ora}=      Fetch From Left    ${kezdes}    :
            ${perc}=     Fetch From Right   ${kezdes}    :

            ${ora}=      Convert To Integer    ${ora}

            ${kezdes}=   Set Variable    ${ora}:${perc}
            ${vege}=        Strip String    ${times}[1]
            ${ora}=      Fetch From Left    ${vege}    :
            ${perc}=     Fetch From Right   ${vege}    :

            ${ora}=      Convert To Integer    ${ora}

            ${vege}=     Set Variable    ${ora}:${perc}

            ${nev_parts}=    Split String    ${user_txt}    :
            ${nev}=          Set Variable    ${nev_parts}[1]
            ${nev}=          Strip String    ${nev}

            IF    '${nev}' == '(none)'
                @{nevek}=    Create List    ÜRES
            ELSE
                @{nevek}=    Split String    ${nev}    ,
            END

            ${raktar}=    Set Variable    ÜRES

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

    ${result}=    googlesheet_modified_template.Write All Shifts
    ...    ${rows}

    Log To Console
    ...    GOOGLE=${result}
