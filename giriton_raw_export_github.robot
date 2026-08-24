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

        ${datum_nap}=    Add Time To Date
        ...    ${base_date}
        ...    ${nap} days
        ...    result_format=%d

        ${datum_nap}=    Convert To Integer    ${datum_nap}

        Log To Console
        ...    DATUM=${datum_giriton}

        Select Giriton Date
        ...    ${datum_giriton}
        ...    ${datum_oldal}
        ...    ${datum_nap}

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
Select Giriton Date
    [Arguments]    ${datum_giriton}    ${datum_oldal}    ${datum_nap}
    Set Giriton Date Field
    ...    ${datum_giriton}

    ${loaded}=    Run Keyword And Return Status
    ...    Wait Until Giriton Date Is Loaded
    ...    ${datum_giriton}
    ...    ${datum_oldal}
    ...    ${datum_nap}

    IF    not ${loaded}
        Log To Console
        ...    DATE_INPUT_NOT_APPLIED_TRY_NEXT_ARROW=${datum_giriton}
        FOR    ${attempt}    IN RANGE    8
            Close Giriton Default Values Popup
            Click Giriton Next Day
            ${loaded}=    Run Keyword And Return Status
            ...    Wait Until Giriton Date Is Loaded
            ...    ${datum_giriton}
            ...    ${datum_oldal}
            ...    ${datum_nap}
            IF    ${loaded}
                BREAK
            END
        END
        IF    not ${loaded}
            Wait Until Giriton Date Is Loaded
            ...    ${datum_giriton}
            ...    ${datum_oldal}
            ...    ${datum_nap}
        END
    END


Set Giriton Date Field
    [Arguments]    ${datum_giriton}
    ${set_result}=    Execute Javascript
    ...    const expected=String(arguments[0] || '').trim();
    ...    const visible=function(el){return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;};
    ...    const looksLikeDate=function(value){value=String(value || '').trim(); return value.indexOf('/') > -1 && value.length >= 8 && value.length <= 10;};
    ...    const inputs=Array.from(document.querySelectorAll('input.v-datefield-textfield, input[class*="v-datefield-textfield"]')).filter(visible);
    ...    const candidates=inputs.filter(function(input){const value=String(input.value || '').trim(); const placeholder=String(input.getAttribute('placeholder') || '').trim(); return looksLikeDate(value) || looksLikeDate(placeholder) || input.closest('.v-datefield');});
    ...    const input=candidates.find(function(item){return looksLikeDate(item.value);}) || candidates[0] || inputs[0];
    ...    if(!input){return 'DATE_INPUT_NOT_FOUND';}
    ...    input.scrollIntoView({block:'center', inline:'nearest'});
    ...    input.focus();
    ...    input.value=expected;
    ...    input.dispatchEvent(new Event('input', {bubbles:true}));
    ...    input.dispatchEvent(new Event('change', {bubbles:true}));
    ...    input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));
    ...    input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));
    ...    input.blur();
    ...    return input.value || '';
    ...    ARGUMENTS
    ...    ${datum_giriton}
    Should Not Be Equal As Strings
    ...    ${set_result}
    ...    DATE_INPUT_NOT_FOUND
    Sleep    4s


Wait Until Giriton Date Is Loaded
    [Arguments]    ${datum_giriton}    ${datum_oldal}    ${datum_nap}
    Wait Until Keyword Succeeds
    ...    30x
    ...    1s
    ...    Giriton Selected Date Should Be
    ...    ${datum_giriton}
    ...    ${datum_oldal}
    ...    ${datum_nap}
    Wait Until Keyword Succeeds
    ...    30x
    ...    1s
    ...    Giriton Loading Should Be Finished
    Wait Until Page Contains Element
    ...    xpath=//div[contains(@class,'panel-title')]
    ...    timeout=30s
    Sleep    2s


Giriton Selected Date Should Be
    [Arguments]    ${datum_giriton}    ${datum_oldal}    ${datum_nap}
    ${date_state}=    Execute Javascript
    ...    const input = document.querySelector('input.v-datefield-textfield'); const value = input ? (input.value || '').trim() : ''; const bodyText = document.body ? document.body.innerText : ''; return 'datefield=' + value + '\\n' + bodyText;
    ${datefield_ok}=    Run Keyword And Return Status
    ...    Should Contain
    ...    ${date_state}
    ...    datefield=${datum_giriton}
    ${visible_date_ok}=    Run Keyword And Return Status
    ...    Should Contain
    ...    ${date_state}
    ...    ${datum_oldal}
    ${day_number_ok}=    Run Keyword And Return Status
    ...    Should Match Regexp
    ...    ${date_state}
    ...    (?m)^\\s*${datum_nap}\\s*\\n\\s*Online\\s*$
    Should Be True
    ...    ${datefield_ok} or ${visible_date_ok} or ${day_number_ok}
    ...    msg=Giriton oldal nem a kert napot mutatja. Kert datum: ${datum_giriton} / ${datum_oldal}. Allapot: ${date_state}


Click Giriton Next Day
    ${click_result}=    Execute Javascript
    ...    const visible=function(el){return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;};
    ...    const textOf=function(el){return String(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();};
    ...    const clickReal=function(el){el.scrollIntoView({block:'center', inline:'center'}); const rect=el.getBoundingClientRect(); const x=rect.left + rect.width / 2; const y=rect.top + rect.height / 2; const target=document.elementFromPoint(x, y) || el; ['mouseover','mousemove','mousedown','mouseup','click'].forEach(function(type){target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y}));});};
    ...    const all=Array.from(document.querySelectorAll('.v-button, button, span, div')).filter(visible);
    ...    const arrows=all.map(function(el){return el.closest('.v-button, button') || el;}).filter(function(el, index, array){return array.indexOf(el) === index;}).filter(function(el){const rect=el.getBoundingClientRect(); const text=textOf(el); const inWindow=!!el.closest('.v-window'); const small=rect.width <= 80 && rect.height <= 80; const topToolbar=rect.top >= 0 && rect.top < 170; return !inWindow && small && topToolbar && (text === '' || text === '>' || text.toLowerCase() === 'next' || text.includes(''));}).sort(function(a,b){const ar=a.getBoundingClientRect(); const br=b.getBoundingClientRect(); return ar.top - br.top || ar.left - br.left;});
    ...    const nextButton=arrows[0];
    ...    if(!nextButton){return 'NEXT_BUTTON_NOT_FOUND';}
    ...    clickReal(nextButton);
    ...    return 'OK';
    Should Be Equal As Strings
    ...    ${click_result}
    ...    OK
    Sleep    3s


Close Giriton Default Values Popup
    Execute Javascript
    ...    const visible=function(el){return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;}; const windows=Array.from(document.querySelectorAll('.v-window')).filter(visible); for(const win of windows){const text=String(win.innerText || ''); if(!text.includes('Default values')){continue;} const buttons=Array.from(win.querySelectorAll('.v-button, button, span, div')).filter(visible); const close=buttons.find(function(el){const label=String(el.innerText || el.textContent || '').trim(); return label === '' || label.toLowerCase() === 'cancel' || label.includes('Cancel');}); if(close){close.click(); return 'CLOSED';}} return 'NO_POPUP';


Giriton Loading Should Be Finished
    ${is_loading}=    Execute Javascript
    ...    return [...document.querySelectorAll('.v-loading-indicator, .v-loading-indicator-delay, .v-loading-indicator-wait')].some(el => { const style = window.getComputedStyle(el); return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'; });
    Should Be Equal
    ...    ${is_loading}
    ...    ${False}
