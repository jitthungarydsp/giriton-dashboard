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

            ${booking_ok}=    Evaluate
            ...    '${add_result}' in ['COURIER_ADDED', 'ALREADY_BOOKED']
            IF    not ${booking_ok}
                Fail
                ...    Eles Giriton foglalas sikertelen: ${add_result}
            END
        ELSE
            ${not_found_screenshot}=    giriton_auto_booking.Build Screenshot Name
            ...    ${candidate}
            ...    shift_not_found
            Capture Page Screenshot    ${not_found_screenshot}

            ${final_status}=    Set Variable If
            ...    '${result}' == 'SHIFT_NOT_EMPTY'
            ...    SHIFT_NOT_EMPTY
            ...    SHIFT_NOT_FOUND
            ${final_message}=    Set Variable If
            ...    '${result}' == 'SHIFT_NOT_EMPTY'
            ...    Megtalaltam a muszakot, de nem 0/X foglaltsagu, ezert nem foglalok. Screenshot: ${loaded_screenshot}, ${not_found_screenshot}
            ...    Nem talaltam a Giriton muszakkartyat erre a raktar/kezdes parra. Screenshot: ${loaded_screenshot}, ${not_found_screenshot}

            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    ${final_status}
            ...    ${final_message}
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

    ${set_result}=    Execute Javascript
    ...    const expected=String('${datum_giriton}').trim();
    ...    const visible=function(el){return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;};
    ...    const looksLikeDate=function(value){value=String(value || '').trim(); return value.indexOf('/') > -1 && value.length >= 8 && value.length <= 10;};
    ...    const inputs=Array.from(document.querySelectorAll('input.v-datefield-textfield, input[class*="v-datefield-textfield"]')).filter(visible);
    ...    const candidates=inputs.filter(function(input){
    ...      const value=String(input.value || '').trim();
    ...      const placeholder=String(input.getAttribute('placeholder') || '').trim();
    ...      return looksLikeDate(value) || looksLikeDate(placeholder) || input.closest('.v-datefield');
    ...    });
    ...    const input=candidates.find(function(item){return looksLikeDate(item.value);}) || candidates[0] || inputs[0];
    ...    if(!input){return 'DATE_INPUT_NOT_FOUND';}
    ...    input.scrollIntoView();
    ...    input.focus();
    ...    input.value=expected;
    ...    input.dispatchEvent(new Event('input', {bubbles:true}));
    ...    input.dispatchEvent(new Event('change', {bubbles:true}));
    ...    input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true}));
    ...    input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));
    ...    input.blur();
    ...    input.setAttribute('data-auto-book-date-target','true');
    ...    return input.value || '';

    Should Not Be Equal As Strings
    ...    ${set_result}
    ...    DATE_INPUT_NOT_FOUND

    Sleep    4s

    ${actual}=    Execute Javascript
    ...    const input=document.querySelector('input[data-auto-book-date-target="true"]');
    ...    return input ? String(input.value || '').trim() : '';

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
        ...    const normalize=function(value){return String(value || '').trim().split(' ').filter(Boolean).join(' ');};
        ...    const toMinutes=function(value){const parts=String(value || '').split(':'); if(parts.length<2){return null;} const h=parseInt(parts[0],10); const m=parseInt(parts[1],10); if(Number.isNaN(h) || Number.isNaN(m)){return null;} return h*60+m;};
        ...    const toTime=function(total, padHour){total=(total+1440)%1440; const h=Math.floor(total/60); const m=total%60; const hh=padHour && h<10 ? '0'+h : String(h); const mm=m<10 ? '0'+m : String(m); return hh + ':' + mm;};
        ...    const baseMinutes=toMinutes(start);
        ...    const offsets=[0,-15,15,-30,30];
        ...    const targetTimes=baseMinutes === null ? [start] : offsets.flatMap(function(offset){const minute=baseMinutes+offset; const padded=toTime(minute,true); const plain=toTime(minute,false); return padded === plain ? [plain] : [padded, plain];});
        ...    const startVariants=targetTimes.flatMap(function(time){return [warehouse + '_' + time, time + ':1k', time + ':', time + ' -', time + '-'];}).map(normalize);
        ...    const hasOpenCapacity=function(value){const compact=String(value || '').split(' ').join(''); for(let i=1;i<=99;i++){if(compact.includes('0/' + i)){return true;}} return false;};
        ...    const titles=[...document.querySelectorAll('div.panel-title')];
        ...    for(const title of titles){
        ...      let node=title;
        ...      for(let depth=0; node && depth<8; depth++, node=node.parentElement){
        ...        const text=normalize(node.innerText || '');
        ...        if(!text.includes(warehouse)){continue;}
        ...        if(!startVariants.some(item => item && text.includes(item))){continue;}
        ...        const matchedTime=targetTimes.find(function(time){return text.includes(warehouse + '_' + time) || text.includes(time + ':1k') || text.includes(time + ':') || text.includes(time + ' -') || text.includes(time + '-');}) || start;
        ...        const compactText=text.replaceAll(' ', '');
        ...        if(!hasOpenCapacity(compactText)){title.scrollIntoView({block:'center', inline:'nearest'}); return 'SHIFT_NOT_EMPTY';}
        ...        const card=node || title;
        ...        title.scrollIntoView({block:'center', inline:'nearest'});
        ...        if(dryRun){return 'FOUND_DRY_RUN';}
        ...        card.setAttribute('data-auto-book-clicked-shift','true');
        ...        card.setAttribute('data-auto-book-matched-shift-start', matchedTime);
        ...        const clickables=[title].concat(Array.from(card.querySelectorAll('.subscribed-persons-label, .v-label, .v-progressbar, .v-progressbar-wrapper, .v-progressbar-indicator, div, span')).filter(function(el){return el.offsetWidth > 0 && el.offsetHeight > 0;}));
        ...        for(const clickable of clickables.slice(0,12)){
        ...          clickable.scrollIntoView({block:'center', inline:'nearest'});
        ...          ['mouseover','mousemove','mousedown','mouseup','click','dblclick'].forEach(function(type){
        ...            clickable.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
        ...          });
        ...          if(document.querySelector('.v-window, [data-auto-book-popup-root="true"], #SearchField-tfTextSearch')){return 'FOUND_CLICKED';}
        ...        }
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
        ...    ARGUMENTS
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

    Wait Until Keyword Succeeds
    ...    10x
    ...    1s
    ...    Giriton Shift Popup Should Be Open

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_POPUP_WAIT_DONE
    ...    Shift subscription popup betoltott.

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_SUBSCRIBED_TAB_START
    ...    Subscribed users ful megnyitasa indul.

    ${selenium_tab_clicked}=    Run Keyword And Return Status
    ...    Click Element
    ...    xpath=(//div[contains(@class,'v-window')]//*[normalize-space(.)='Subscribed users (0)' or starts-with(normalize-space(.), 'Subscribed users')])[last()]
    ${tab_result}=    Set Variable If    ${selenium_tab_clicked}    OK    NOT_FOUND

    IF    '${tab_result}' != 'OK'
        ${tab_result}=    Execute Javascript
        ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
        ...    const normalize=value => String(value || '').trim().split(' ').filter(Boolean).join(' ');
        ...    const area=el => el.getBoundingClientRect().width * el.getBoundingClientRect().height;
        ...    const clickReal=function(el){
        ...      el.scrollIntoView({block:'center', inline:'center'});
        ...      const rect=el.getBoundingClientRect();
        ...      const x=rect.left + rect.width / 2;
        ...      const y=rect.top + rect.height / 2;
        ...      const real=document.elementFromPoint(x, y) || el;
        ...      ['mouseover','mousemove','mousedown','mouseup','click'].forEach(function(type){
        ...        real.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y}));
        ...      });
        ...    };
        ...    const labels=[...document.querySelectorAll('.v-window .v-captiontext, .v-window .v-tabsheet-tabitem, .v-window td, .v-window div, .v-window span')].filter(visible);
        ...    labels.sort((a,b) => area(a) - area(b));
        ...    const label=labels.find(el => normalize(el.innerText || el.textContent).startsWith('Subscribed users'));
        ...    if(!label){return 'NOT_FOUND';}
        ...    const tab=label.closest('.v-tabsheet-tabitemcell, .v-tabsheet-tabitem, td') || label;
        ...    clickReal(tab);
        ...    clickReal(label);
        ...    return 'OK';
    END

    IF    '${tab_result}' != 'OK'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_SUBSCRIBED_TAB_FAILED
        ...    Subscribed users ful nem talalhato.
        RETURN    SUBSCRIBED_TAB_NOT_FOUND
    END

    Sleep    1s

    ${tab_open}=    Execute Javascript
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    const text=String((document.querySelector('.v-window') || document).innerText || '');
    ...    if(document.querySelector('#SearchField-tfTextSearch')){return 'YES';}
    ...    if(text.includes('Number of persons:') || text.includes('Automatically approve:') || text.includes('Subscribe since:')){return 'NO';}
    ...    const buttons=[...document.querySelectorAll('.v-window .v-button, .v-window [role="button"], .v-window button')].filter(visible);
    ...    return buttons.length > 0 ? 'YES' : 'NO';

    IF    '${tab_open}' != 'YES'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_SUBSCRIBED_TAB_FAILED
        ...    Subscribed users ful kattintas utan sem nyilt meg.
        RETURN    SUBSCRIBED_TAB_NOT_OPEN
    END

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_SUBSCRIBED_TAB_DONE
    ...    Subscribed users ful megnyitva.

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_ALREADY_BOOKED_CHECK_START
    ...    Ellenorzes indul: futar mar szerepel-e a muszakon.

    ${already_added}=    Execute Javascript
    ...    const courierId=String(arguments[0] || '').trim();
    ...    const courierName=String(arguments[1] || '').trim();
    ...    const userNumber=courierId ? 'D' + courierId : '';
    ...    const windows=[...document.querySelectorAll('.v-window')];
    ...    const win=windows[windows.length - 1] || document;
    ...    const text=win.innerText || '';
    ...    if(userNumber && text.includes(userNumber)){return 'YES';}
    ...    if(courierName && text.toLowerCase().includes(courierName.toLowerCase())){return 'YES';}
    ...    return 'NO';
    ...    ARGUMENTS
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
    ...    const visible=function(el){return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;};
    ...    const textOf=function(el){return String(el.innerText || el.textContent || el.getAttribute('title') || el.getAttribute('aria-label') || el.id || el.className || '').trim();};
    ...    const overlays=Array.from(document.querySelectorAll('.v-window, [id$="-overlays"], [id*="-overlays"], .v-popupview-popup, .v-overlay-container')).filter(visible);
    ...    const win=overlays.find(function(el){return textOf(el).includes('Subscribed users') || textOf(el).includes('Available users') || textOf(el).includes('Search');}) || overlays[overlays.length - 1] || document;
    ...    const xpathFirst=document.evaluate('//*[@id="gwt-uid-69"]/div', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    ...    const candidates=[xpathFirst].filter(Boolean).concat(Array.from(win.querySelectorAll('.v-button, [role="button"], button, span, div')).filter(visible));
    ...    const plus=candidates.find(function(button){
    ...      const style=getComputedStyle(button);
    ...      const cls=String(button.className || '').toLowerCase();
    ...      const label=textOf(button).toLowerCase();
    ...      const small=button.offsetWidth <= 80 && button.offsetHeight <= 80;
    ...      return small && (label === '+' || label.includes('add') || label.includes('new') || label.includes('plus') || cls.includes('plus') || cls.includes('add') || cls.includes('friendly') || style.backgroundColor.includes('76, 175, 80'));
    ...    });
    ...    if(!plus){return 'NOT_FOUND';}
    ...    plus.scrollIntoView({block:'center', inline:'nearest'});
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

    Execute Javascript
    ...    const field=document.querySelector('#SearchField-tfTextSearch'); if(field){field.dispatchEvent(new Event('input',{bubbles:true})); field.dispatchEvent(new Event('change',{bubbles:true})); field.blur();}

    Sleep    2s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_SELECT_START
    ...    Futar sor keresese es kivalasztasa indul.

    ${select_result}=    Execute Javascript
    ...    const courierId=String(arguments[0] || '').trim();
    ...    const courierName=String(arguments[1] || '').trim().toLowerCase();
    ...    const email=String(arguments[2] || '').trim().toLowerCase();
    ...    const userNumber=courierId ? 'D' + courierId : '';
    ...    const nameParts=courierName.split(' ').filter(Boolean);
    ...    const reversedName=nameParts.length > 1 ? nameParts.slice(1).join(' ') + ' ' + nameParts[0] : courierName;
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    const dialogs=[...document.querySelectorAll('.v-window')].filter(visible);
    ...    const dialog=dialogs[dialogs.length - 1] || document;
    ...    const rows=[...dialog.querySelectorAll('tr.v-grid-row, tr[role="row"]')];
    ...    const row=rows.find(item => {
    ...      const text=(item.innerText || '').trim().split(' ').filter(Boolean).join(' ');
    ...      const lower=text.toLowerCase();
    ...      if(userNumber && text.includes(userNumber)){return true;}
    ...      if(courierName && lower.includes(courierName)){return true;}
    ...      if(reversedName && lower.includes(reversedName)){return true;}
    ...      if(email && lower.includes(email)){return true;}
    ...      return false;
    ...    });
    ...    if(!row){return 'NOT_FOUND';}
    ...    row.scrollIntoView({block:'center', inline:'nearest'});
    ...    const checkbox=row.querySelector('input[type="checkbox"]');
    ...    if(checkbox){checkbox.click(); return 'OK';}
    ...    row.click();
    ...    return 'OK';
    ...    ARGUMENTS
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
    ...    const userNumber=courierId ? 'D' + courierId : '';
    ...    const windows=[...document.querySelectorAll('.v-window')];
    ...    const win=windows[windows.length - 1] || document;
    ...    const text=(win.innerText || '').toLowerCase();
    ...    const raw=win.innerText || '';
    ...    if(userNumber && raw.includes(userNumber)){return 'COURIER_ADDED';}
    ...    if(courierName && text.includes(courierName)){return 'COURIER_ADDED';}
    ...    return 'COURIER_SELECTED_NOT_VERIFIED';
    ...    ARGUMENTS
    ...    ${courier_id}
    ...    ${courier_name}

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_VERIFY_DONE
    ...    Foglalas ellenorzes eredmenye: ${verify_result}

    RETURN    ${verify_result}


Giriton Shift Popup Should Be Open
    ${popup_state}=    Execute Javascript
    ...    const visible=function(el){return !!el && el.offsetWidth > 0 && el.offsetHeight > 0;};
    ...    const textOf=function(el){return String(el.innerText || el.textContent || '').trim().split(' ').filter(Boolean).join(' ');};
    ...    if(document.querySelector('#SearchField-tfTextSearch')){return 'POPUP_OPEN';}
    ...    const overlays=Array.from(document.querySelectorAll('.v-window, [data-auto-book-popup-root="true"], [id$="-overlays"], [id*="-overlays"], .v-popupview-popup, .v-overlay-container')).filter(visible);
    ...    const popup=overlays.find(function(el){const text=textOf(el); return text.includes('Subscribed users') || text.includes('Available users') || text.includes('Search');});
    ...    if(popup){popup.setAttribute('data-auto-book-popup-root','true'); return 'POPUP_OPEN';}
    ...    return 'POPUP_NOT_OPEN';

    Should Be Equal As Strings
    ...    ${popup_state}
    ...    POPUP_OPEN


Close Giriton Popup
    ${result}=    Execute Javascript
    ...    const windows=[...document.querySelectorAll('.v-window, [data-auto-book-popup-root="true"]')];
    ...    const win=windows[windows.length - 1];
    ...    if(!win){return 'NO_WINDOW';}
    ...    const close=win.querySelector('.v-window-closebox');
    ...    if(close){close.click(); return 'CLOSED';}
    ...    return 'NO_CLOSE';

    Sleep    1s
    RETURN    ${result}
