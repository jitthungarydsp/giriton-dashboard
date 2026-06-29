*** Settings ***
Library    SeleniumLibrary
Library    Collections
Library    String


*** Keywords ***
Collect Visible Giriton Shift Rows
    [Arguments]    ${rows}    ${datum_sheet}

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
    ${db_raktar}=    Get Length    ${raktarak}
    ${db_user}=    Get Length    ${users}
    ${db_fogl}=    Get Length    ${foglaltsagok}
    ${db}=    Evaluate    min(${db}, ${db_raktar}, ${db_user}, ${db_fogl})

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

        ${maximum}=    Strip String
        ...    ${fog_parts}[1]

        ${foglalt_int}=    Convert To Integer    ${foglalt}
        ${maximum_int}=    Convert To Integer    ${maximum}

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
