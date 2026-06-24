*** Settings ***
Library    SeleniumLibrary
Library    googlesheet.py
Library    SeleniumLibrary
Library    DateTime
Library    String


*** Keywords ***
Bejelentkezes
    Open Browser    https://kiflihu.giriton.com/    chrome    executable_path=C:/Giriton/giriton-dashboard/Drivers/chromedriver
    Maximize Browser Window
    Wait Until Element Is Visible    locator=//*[@id="CompanyLoginPanel-tfUserLogin"]
    SeleniumLibrary.Input Text    locator=//*[@id="CompanyLoginPanel-tfUserLogin"]    text=jitthungary@gmail.com
    SeleniumLibrary.Input Text        locator=//*[@id="CompanyLoginPanel-pfUserPassword"]           text=ujjelszo15
    Click Element            locator=//*[@id="ROOT-2521314"]/div/div[2]/div/div/div/div[3]/div/div[3]/div/div[1]/div

Slack login
    Open Browser    https://app.slack.com/client/E01R5ED1R0U/C0B6B3F5S31    chrome    executable_path=C:/Giriton/robots/Drivers/chromedriver
    Maximize Browser Window
    Sleep    20


Click Shift Subs
    SeleniumLibrary.Wait Until Element Is Visible    locator=//*[@id="layMenuItems"]/div[5]/div/span
    SeleniumLibrary.Click Element    locator=//*[@id="layMenuItems"]/div[5]/div/span

Beallit Datum

    [Arguments]    ${datum}

    Click Element
    ...    xpath=//input[contains(@class,'v-datefield-textfield')]

    Press Keys
    ...    xpath=//input[contains(@class,'v-datefield-textfield')]
    ...    CTRL+A

    Input Text
    ...    xpath=//input[contains(@class,'v-datefield-textfield')]
    ...    ${datum}

    Press Keys
    ...    xpath=//input[contains(@class,'v-datefield-textfield')]
    ...    ENTER

    Sleep    3

Muszakok Kiolvasasa

     # ===== Összes műszak betöltése =====

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
            Append To List    ${uj_foglaltsagok}    ${foglaltsagok}[${i}]
        END

    END