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
${AUTO_BOOK_SERIAL}
${AUTO_BOOK_COURIER_ID}
${AUTO_BOOK_EMAIL}


*** Test Cases ***
Giriton Auto Booking From Foglalasok
    Log To Console    GIRITON_AUTO_BOOKING_VERSION=t_plus_3_foglalasok_dry_run

    ${empty_candidate}=    Create Dictionary
    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_LOGIN_START
    ...    Giriton bejelentkezes indul.

    keywords_github.Bejelentkezes

    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_LOGIN_DONE
    ...    Giriton bejelentkezes kesz.

    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_SHIFT_SUBS_OPEN_START
    ...    Shift Subscription oldal megnyitasa indul.

    keywords_github.Click Shift Subs

    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_SHIFT_SUBS_OPEN_DONE
    ...    Shift Subscription oldal megnyitva.

    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_DEPARTMENT_SELECT_START
    ...    Osszes department/raktar kivalasztasa indul.

    keywords_github.Select All Departments

    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_DEPARTMENT_SELECT_DONE
    ...    Osszes department/raktar kivalasztva.

    Sleep    10s

    @{candidates}=    giriton_auto_booking.Get T Plus Booking Candidates
    ...    ${AUTO_BOOK_DAYS_AHEAD}
    ...    ${AUTO_BOOK_HORIZON_DAYS}
    ...    ${AUTO_BOOK_START_DATE}
    ...    ${AUTO_BOOK_END_DATE}
    ...    10000
    ...    ${AUTO_BOOK_SERIAL}
    ...    ${AUTO_BOOK_COURIER_ID}
    ...    ${AUTO_BOOK_EMAIL}

    ${candidate_count}=    Get Length    ${candidates}
    Log To Console    AUTO_BOOK_CANDIDATES=${candidate_count}
    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_CANDIDATES_LOADED
    ...    Feldolgozhato jeloltek szama: ${candidate_count}

    FOR    ${candidate}    IN    @{candidates}
        ${work_date}=       Set Variable    ${candidate}[work_date]
        ${giriton_date}=    Set Variable    ${candidate}[giriton_date]
        ${warehouse}=       Set Variable    ${candidate}[warehouse]
        ${shift_start}=     Set Variable    ${candidate}[shift_start]
        ${courier_name}=    Set Variable    ${candidate}[courier_name]
        ${email}=           Set Variable    ${candidate}[email]

        Log To Console
        ...    AUTO_BOOK_ITEM ${work_date} ${warehouse} ${shift_start} ${courier_name} ${email}

        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_CANDIDATE_START
        ...    Jelolt feldolgozasa indul: ${work_date} ${warehouse} ${shift_start} ${courier_name} ${email}

        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_DATE_SET_START
        ...    Giriton datum beallitasa indul: ${giriton_date}

        Beallit Giriton Datum
        ...    ${giriton_date}

        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_DATE_SET_DONE
        ...    Giriton datum beallitva: ${giriton_date}

        ${loaded_screenshot}=    giriton_auto_booking.Build Screenshot Name
        ...    ${candidate}
        ...    page_loaded
        Capture Page Screenshot    ${loaded_screenshot}

        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_PAGE_LOADED_SCREENSHOT_DONE
        ...    Oldal betoltes utani screenshot kesz: ${loaded_screenshot}

        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_SHIFT_SEARCH_START
        ...    Muszakkartya keresese indul: ${warehouse} ${shift_start}

        ${result}=    Find Giriton Shift Card
        ...    ${warehouse}
        ...    ${shift_start}
        ...    ${AUTO_BOOK_DRY_RUN}

        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_SHIFT_SEARCH_DONE
        ...    Muszakkartya kereses eredmenye: ${result}

        IF    '${result}' == 'FOUND_DRY_RUN'
            ${found_screenshot}=    giriton_auto_booking.Build Screenshot Name
            ...    ${candidate}
            ...    dry_run_shift_found
            Capture Page Screenshot    ${found_screenshot}

            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    DRY_RUN_FOUND
            ...    A Giriton muszakkartya megvan, eles kattintas kihagyva. Screenshot: ${loaded_screenshot}, ${found_screenshot}
        ELSE IF    '${result}' == 'FOUND_CLICKED'
            Log Auto Booking Step
            ...    ${candidate}
            ...    STEP_BOOKING_FLOW_START
            ...    Eles foglalasi folyamat indul.

            ${add_result}=    Add Courier To Shift Subscription
            ...    ${candidate}

            Log Auto Booking Step
            ...    ${candidate}
            ...    STEP_BOOKING_FLOW_DONE
            ...    Eles foglalasi folyamat eredmenye: ${add_result}

            ${booking_screenshot}=    giriton_auto_booking.Build Screenshot Name
            ...    ${candidate}
            ...    booking_result
            Capture Page Screenshot    ${booking_screenshot}

            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    ${add_result}
            ...    A Giriton muszakkartya megvan, a futar hozzaadasi folyamat lefutott. Screenshot: ${loaded_screenshot}, ${booking_screenshot}

            Close Giriton Popup
        ELSE
            ${not_found_screenshot}=    giriton_auto_booking.Build Screenshot Name
            ...    ${candidate}
            ...    shift_not_found
            Capture Page Screenshot    ${not_found_screenshot}

            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    SHIFT_NOT_FOUND
            ...    Nem talaltam a Giriton muszakkartyat erre a raktar/kezdes parra. Screenshot: ${loaded_screenshot}, ${not_found_screenshot}
        END

        Log To Console    AUTO_BOOK_RESULT=${result} LOG=${log_result}
    END


*** Keywords ***
Log Auto Booking Step
    [Arguments]    ${candidate}    ${status}    ${message}

    ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
    ...    ${candidate}
    ...    ${status}
    ...    ${message}

    Log To Console    AUTO_BOOK_STEP=${status} LOG=${log_result}
    RETURN    ${log_result}


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


Add Courier To Shift Subscription
    [Arguments]    ${candidate}

    ${courier_name}=    Set Variable    ${candidate}[courier_name]
    ${courier_id}=      Set Variable    ${candidate}[courier_id]
    ${email}=           Set Variable    ${candidate}[email]

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_POPUP_WAIT_START
    ...    Shift subscription popup betoltesere var.

    Wait Until Page Contains
    ...    Shift subscription
    ...    timeout=20s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_POPUP_WAIT_DONE
    ...    Shift subscription popup betoltott.

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_SUBSCRIBED_TAB_START
    ...    Subscribed users ful megnyitasa indul.

    ${tab_result}=    Execute Javascript
    ...    const tabs=[...document.querySelectorAll('.v-tabsheet-tabitem, .v-caption, .v-captiontext, td[role="tab"]')];
    ...    const tab=tabs.find(el => (el.innerText || '').includes('Subscribed users') && el.offsetWidth >= 0);
    ...    if(tab){tab.click(); return 'OK';}
    ...    return 'NOT_FOUND';

    IF    '${tab_result}' != 'OK'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_SUBSCRIBED_TAB_FAILED
        ...    Subscribed users ful nem talalhato.
        RETURN    SUBSCRIBED_TAB_NOT_FOUND
    END

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_SUBSCRIBED_TAB_DONE
    ...    Subscribed users ful megnyitva.

    Sleep    1s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_ALREADY_BOOKED_CHECK_START
    ...    Ellenorzes indul: futar mar szerepel-e a muszakon.

    ${already_added}=    Execute Javascript
    ...    const courierId=String(arguments[0] || '').trim();
    ...    const courierName=String(arguments[1] || '').trim();
    ...    const userNumber=courierId ? `D${courierId}` : '';
    ...    const windows=[...document.querySelectorAll('.v-window')];
    ...    const win=windows[windows.length - 1] || document;
    ...    const text=win.innerText || '';
    ...    if(userNumber && text.includes(userNumber)){return 'YES';}
    ...    if(courierName && text.toLowerCase().includes(courierName.toLowerCase())){return 'YES';}
    ...    return 'NO';
    ...    ${courier_id}
    ...    ${courier_name}

    IF    '${already_added}' == 'YES'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_ALREADY_BOOKED_FOUND
        ...    A futar mar szerepel a subscribed users listaban.
        RETURN    ALREADY_BOOKED
    END

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_ALREADY_BOOKED_CHECK_DONE
    ...    A futar meg nincs a subscribed users listaban.

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_ADD_BUTTON_START
    ...    Zold plusz gomb keresese/megnyomasa indul.

    ${plus_result}=    Execute Javascript
    ...    const windows=[...document.querySelectorAll('.v-window')];
    ...    const win=windows[windows.length - 1] || document;
    ...    const buttons=[...win.querySelectorAll('.v-button')];
    ...    const plus=buttons.find(button => {
    ...      const style=getComputedStyle(button);
    ...      const cls=String(button.className || '');
    ...      return button.offsetWidth > 0 && button.offsetHeight > 0 && (cls.includes('friendly') || cls.includes('v-button-friendly') || style.backgroundColor.includes('76, 175, 80'));
    ...    });
    ...    if(!plus){return 'NOT_FOUND';}
    ...    plus.click();
    ...    return 'OK';

    IF    '${plus_result}' != 'OK'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_ADD_BUTTON_FAILED
        ...    Zold plusz gomb nem talalhato.
        RETURN    ADD_BUTTON_NOT_FOUND
    END

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_ADD_BUTTON_DONE
    ...    Zold plusz gomb megnyomva.

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_SEARCH_FIELD_WAIT_START
    ...    Futar kereso mezo betoltesere var.

    Wait Until Element Is Visible
    ...    xpath=//*[@id="SearchField-tfTextSearch"]
    ...    timeout=20s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_SEARCH_FIELD_WAIT_DONE
    ...    Futar kereso mezo betoltott.

    Click Element
    ...    xpath=//*[@id="SearchField-tfTextSearch"]

    Press Keys
    ...    xpath=//*[@id="SearchField-tfTextSearch"]
    ...    CTRL+A

    ${search_text}=    Set Variable If    '${courier_name}' != ''    ${courier_name}    ${email}

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_SEARCH_INPUT_START
    ...    Futar keresesi szoveg beirasa indul: ${search_text}

    Input Text
    ...    xpath=//*[@id="SearchField-tfTextSearch"]
    ...    ${search_text}

    Sleep    2s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_SELECT_START
    ...    Futar sor keresese es kivalasztasa indul.

    ${select_result}=    Execute Javascript
    ...    const courierId=String(arguments[0] || '').trim();
    ...    const courierName=String(arguments[1] || '').trim().toLowerCase();
    ...    const email=String(arguments[2] || '').trim().toLowerCase();
    ...    const userNumber=courierId ? `D${courierId}` : '';
    ...    const nameParts=courierName.split(/\s+/).filter(Boolean);
    ...    const reversedName=nameParts.length > 1 ? `${nameParts.slice(1).join(' ')} ${nameParts[0]}` : courierName;
    ...    const dialogs=[...document.querySelectorAll('.v-window')];
    ...    const dialog=dialogs[dialogs.length - 1] || document;
    ...    const rows=[...dialog.querySelectorAll('tr.v-grid-row, tr[role="row"]')];
    ...    const row=rows.find(item => {
    ...      const text=(item.innerText || '').replace(/\s+/g,' ').trim();
    ...      const lower=text.toLowerCase();
    ...      if(userNumber && text.includes(userNumber)){return true;}
    ...      if(courierName && lower.includes(courierName)){return true;}
    ...      if(reversedName && lower.includes(reversedName)){return true;}
    ...      if(email && lower.includes(email)){return true;}
    ...      return false;
    ...    });
    ...    if(!row){return 'NOT_FOUND';}
    ...    const checkbox=row.querySelector('input[type="checkbox"]');
    ...    if(checkbox){checkbox.click(); return 'OK';}
    ...    row.click();
    ...    return 'OK';
    ...    ${courier_id}
    ...    ${courier_name}
    ...    ${email}

    IF    '${select_result}' != 'OK'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_COURIER_SELECT_FAILED
        ...    Futar sor nem talalhato vagy nem kivalaszthato.
        RETURN    COURIER_NOT_FOUND
    END

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_SELECT_DONE
    ...    Futar sor kivalasztva.

    Sleep    1s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_CHOOSE_BUTTON_START
    ...    Choose/megerosito gomb keresese/megnyomasa indul.

    ${choose_result}=    Execute Javascript
    ...    const button=document.querySelector('#SelectionDialog-btn-confirm-selection') || [...document.querySelectorAll('.v-button')].find(el => (el.innerText || '').includes('Choose') && el.offsetWidth > 0 && el.offsetHeight > 0);
    ...    if(!button){return 'NOT_FOUND';}
    ...    button.click();
    ...    return 'OK';

    IF    '${choose_result}' != 'OK'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_CHOOSE_BUTTON_FAILED
        ...    Choose/megerosito gomb nem talalhato.
        RETURN    CHOOSE_BUTTON_NOT_FOUND
    END

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_CHOOSE_BUTTON_DONE
    ...    Choose/megerosito gomb megnyomva.

    Sleep    2s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_VERIFY_START
    ...    Foglalas eredmenyenek ellenorzese indul.

    ${verify_result}=    Execute Javascript
    ...    const courierId=String(arguments[0] || '').trim();
    ...    const courierName=String(arguments[1] || '').trim().toLowerCase();
    ...    const userNumber=courierId ? `D${courierId}` : '';
    ...    const windows=[...document.querySelectorAll('.v-window')];
    ...    const win=windows[windows.length - 1] || document;
    ...    const text=(win.innerText || '').toLowerCase();
    ...    const raw=win.innerText || '';
    ...    if(userNumber && raw.includes(userNumber)){return 'COURIER_ADDED';}
    ...    if(courierName && text.includes(courierName)){return 'COURIER_ADDED';}
    ...    return 'COURIER_SELECTED_NOT_VERIFIED';
    ...    ${courier_id}
    ...    ${courier_name}

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_VERIFY_DONE
    ...    Foglalas ellenorzes eredmenye: ${verify_result}

    RETURN    ${verify_result}


Close Giriton Popup
    ${result}=    Execute Javascript
    ...    const windows=[...document.querySelectorAll('.v-window')];
    ...    const win=windows[windows.length - 1];
    ...    if(!win){return 'NO_WINDOW';}
    ...    const close=win.querySelector('.v-window-closebox');
    ...    if(close){close.click(); return 'CLOSED';}
    ...    return 'NO_CLOSE';

    Sleep    1s
    RETURN    ${result}
