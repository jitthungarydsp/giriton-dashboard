*** Settings ***
Resource    resources/keywords_github.robot
Resource    resources/variables.robot
Library    resources/giriton_auto_booking.py
Library    SeleniumLibrary
Library    Collections
Library    DateTime
Library    String


*** Variables ***
${AUTO_BOOK_DAYS_AHEAD}      3
${AUTO_BOOK_HORIZON_DAYS}    1
${AUTO_BOOK_START_DATE}
${AUTO_BOOK_END_DATE}
${AUTO_BOOK_DRY_RUN}         true


*** Test Cases ***
Giriton Auto Booking From Foglalasok
    Log To Console    GIRITON_AUTO_BOOKING_VERSION=t_plus_3_foglalasok_dry_run

    keywords_github.Bejelentkezes
    keywords_github.Click Shift Subs
    keywords_github.Select All Departments

    Sleep    10s

    @{candidates}=    giriton_auto_booking.Get T Plus Booking Candidates
    ...    ${AUTO_BOOK_DAYS_AHEAD}
    ...    ${AUTO_BOOK_HORIZON_DAYS}
    ...    ${AUTO_BOOK_START_DATE}
    ...    ${AUTO_BOOK_END_DATE}

    ${candidate_count}=    Get Length    ${candidates}
    Log To Console    AUTO_BOOK_CANDIDATES=${candidate_count}

    FOR    ${candidate}    IN    @{candidates}
        ${work_date}=       Set Variable    ${candidate}[work_date]
        ${giriton_date}=    Set Variable    ${candidate}[giriton_date]
        ${warehouse}=       Set Variable    ${candidate}[warehouse]
        ${shift_start}=     Set Variable    ${candidate}[shift_start]
        ${courier_name}=    Set Variable    ${candidate}[courier_name]
        ${email}=           Set Variable    ${candidate}[email]

        Log To Console
        ...    AUTO_BOOK_ITEM ${work_date} ${warehouse} ${shift_start} ${courier_name} ${email}

        Beallit Giriton Datum
        ...    ${giriton_date}

        ${result}=    Find Giriton Shift Card
        ...    ${warehouse}
        ...    ${shift_start}
        ...    ${AUTO_BOOK_DRY_RUN}

        IF    '${result}' == 'FOUND_DRY_RUN'
            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    DRY_RUN_FOUND
            ...    A Giriton muszakkartya megvan, eles kattintas kihagyva.
        ELSE IF    '${result}' == 'FOUND_CLICKED'
            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    SHIFT_CLICKED
            ...    A Giriton muszakkartya megvan es kattintva lett. A futar hozzaadas modal meg kulon bekotes.
        ELSE
            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    SHIFT_NOT_FOUND
            ...    Nem talaltam a Giriton muszakkartyat erre a raktar/kezdes parra.
        END

        Log To Console    AUTO_BOOK_RESULT=${result} LOG=${log_result}
    END


*** Keywords ***
Beallit Giriton Datum
    [Arguments]    ${datum_giriton}

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

    Execute Javascript
    ...    document.activeElement && document.activeElement.blur && document.activeElement.blur();

    Sleep    4s

    ${actual}=    Get Element Attribute
    ...    xpath=//input[contains(@class,'v-datefield-textfield')]
    ...    value

    Should Be Equal As Strings
    ...    ${actual}
    ...    ${datum_giriton}


Find Giriton Shift Card
    [Arguments]    ${warehouse}    ${shift_start}    ${dry_run}=true

    Execute Javascript
    ...    let els=[...document.querySelectorAll('*')]; let scrollable=els.filter(e=>e.scrollHeight>e.clientHeight); let biggest=scrollable.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0]; if(biggest){biggest.scrollTop=0;}

    Sleep    1s

    FOR    ${i}    IN RANGE    20
        ${result}=    Execute Javascript
        ...    const warehouse=String(arguments[0] || '').trim().toUpperCase();
        ...    const start=String(arguments[1] || '').trim();
        ...    const dryRun=String(arguments[2] || 'true').toLowerCase() !== 'false';
        ...    const normalize=(value)=>String(value || '').replace(/\s+/g,' ').trim();
        ...    const startVariants=[`${warehouse}_${start}`, `${start}:1k`, `${start}:`, `${start} -`, `${start}-`].map(normalize);
        ...    const titles=[...document.querySelectorAll('div.panel-title')];
        ...    for(const title of titles){
        ...      let node=title;
        ...      for(let depth=0; node && depth<8; depth++, node=node.parentElement){
        ...        const text=normalize(node.innerText || '');
        ...        if(!text.includes(warehouse)){continue;}
        ...        if(!startVariants.some(item => item && text.includes(item))){continue;}
        ...        title.scrollIntoView({block:'center', inline:'nearest'});
        ...        if(dryRun){return 'FOUND_DRY_RUN';}
        ...        title.click();
        ...        return 'FOUND_CLICKED';
        ...      }
        ...    }
        ...    const scrollables=[...document.querySelectorAll('*')].filter(e=>e.scrollHeight>e.clientHeight);
        ...    const biggest=scrollables.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0];
        ...    if(biggest && biggest.scrollTop + biggest.clientHeight < biggest.scrollHeight - 5){
        ...      biggest.scrollTop = biggest.scrollTop + Math.max(400, biggest.clientHeight * 0.85);
        ...      return 'CONTINUE';
        ...    }
        ...    return 'NOT_FOUND';
        ...    ${warehouse}
        ...    ${shift_start}
        ...    ${dry_run}

        IF    '${result}' != 'CONTINUE'
            RETURN    ${result}
        END

        Sleep    1s
    END

    RETURN    NOT_FOUND
