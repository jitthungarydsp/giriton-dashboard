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
${AUTO_BOOK_WAREHOUSE}
${AUTO_BOOK_SHIFT_START}
${AUTO_BOOK_PLAN_JSON}


*** Test Cases ***
Giriton Auto Booking From Foglalasok
    ${auto_book_mode}=    Set Variable If
    ...    '${AUTO_BOOK_DRY_RUN}' == 'false'
    ...    LIVE
    ...    DRY_RUN
    Log To Console    GIRITON_AUTO_BOOKING_VERSION=t_plus_3_foglalasok
    Log To Console    AUTO_BOOK_MODE=${auto_book_mode} AUTO_BOOK_DRY_RUN=${AUTO_BOOK_DRY_RUN}
    Log To Console    AUTO_BOOK_FILTER start=${AUTO_BOOK_START_DATE} end=${AUTO_BOOK_END_DATE} serial=${AUTO_BOOK_SERIAL} email=${AUTO_BOOK_EMAIL} warehouse=${AUTO_BOOK_WAREHOUSE} shift_start=${AUTO_BOOK_SHIFT_START}

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
    ...    ${AUTO_BOOK_WAREHOUSE}
    ...    ${AUTO_BOOK_SHIFT_START}
    ...    ${AUTO_BOOK_PLAN_JSON}

    ${candidate_count}=    Get Length    ${candidates}
    Log To Console    AUTO_BOOK_CANDIDATES=${candidate_count}
    Log Auto Booking Step
    ...    ${empty_candidate}
    ...    STEP_CANDIDATES_LOADED
    ...    Feldolgozhato jeloltek szama: ${candidate_count}

    ${is_targeted_live}=    Evaluate    str($AUTO_BOOK_DRY_RUN).lower() == "false" and bool(str($AUTO_BOOK_SERIAL).strip())
    IF    ${is_targeted_live} and ${candidate_count} != 1
        Log To Console    AUTO_BOOK_RESULT=TARGETED_SERIAL_CANDIDATE_COUNT_INVALID serial=${AUTO_BOOK_SERIAL} candidates=${candidate_count}
        Fail    Eles serialos foglalasnal pontosan 1 jelolt kell, kapott jeloltek szama: ${candidate_count}
    END

    ${current_giriton_date}=    Set Variable    ${EMPTY}

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

        IF    '${current_giriton_date}' != '${giriton_date}'
            Log Auto Booking Step
            ...    ${candidate}
            ...    STEP_DATE_SET_START
            ...    Giriton datum beallitasa indul: ${giriton_date}

            ${date_set_ok}=    Run Keyword And Return Status
            ...    Wait Until Keyword Succeeds
            ...    3x
            ...    5s
            ...    Beallit Giriton Datum
            ...    ${giriton_date}

            IF    not ${date_set_ok}
                Log Auto Booking Step
                ...    ${candidate}
                ...    STEP_DATE_SET_REOPEN_SHIFT_SUBS
                ...    Datummezo nem talalhato, Shift Subscription oldal ujranyitasa indul: ${giriton_date}
                keywords_github.Click Shift Subs
                Sleep    3s
                ${date_set_ok}=    Run Keyword And Return Status
                ...    Wait Until Keyword Succeeds
                ...    2x
                ...    5s
                ...    Beallit Giriton Datum
                ...    ${giriton_date}
            END

            IF    not ${date_set_ok}
                ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
                ...    ${candidate}
                ...    DATE_INPUT_NOT_FOUND
                ...    Nem talalhato a Giriton datummezo, a robot a kovetkezo listatagra lep.
                Log To Console    AUTO_BOOK_RESULT=DATE_INPUT_NOT_FOUND LOG=${log_result}
                CONTINUE
            END

            ${current_giriton_date}=    Set Variable    ${giriton_date}

            Log Auto Booking Step
            ...    ${candidate}
            ...    STEP_DATE_SET_DONE
            ...    Giriton datum beallitva: ${giriton_date}
        ELSE
            Log Auto Booking Step
            ...    ${candidate}
            ...    STEP_DATE_SET_SKIPPED
            ...    Giriton datum mar be van allitva, ujraallitas kihagyva: ${giriton_date}
        END

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

        IF    $result == 'FOUND_DRY_RUN'
            ${found_screenshot}=    giriton_auto_booking.Build Screenshot Name
            ...    ${candidate}
            ...    dry_run_shift_found
            Capture Page Screenshot    ${found_screenshot}

            ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
            ...    ${candidate}
            ...    DRY_RUN_FOUND
            ...    A Giriton muszakkartya megvan, eles kattintas kihagyva. Screenshot: ${loaded_screenshot}, ${found_screenshot}
        ELSE IF    $result == 'FOUND_CLICKED'
            Log Auto Booking Step
            ...    ${candidate}
            ...    STEP_BOOKING_FLOW_START
            ...    Eles foglalasi folyamat indul.

            ${add_status}    ${add_result}=    Run Keyword And Ignore Error
            ...    Add Courier To Shift Subscription
            ...    ${candidate}

            IF    '${add_status}' != 'PASS'
                ${booking_screenshot}=    giriton_auto_booking.Build Screenshot Name
                ...    ${candidate}
                ...    booking_error
                Capture Page Screenshot    ${booking_screenshot}
                ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
                ...    ${candidate}
                ...    BOOKING_FLOW_ERROR
                ...    Giriton foglalasi folyamat hiba, kovetkezo listatagra lepek. Hiba: ${add_result}. Screenshot: ${loaded_screenshot}, ${booking_screenshot}
                Close Giriton Popup
                Log To Console    AUTO_BOOK_RESULT=BOOKING_FLOW_ERROR LOG=${log_result}
                CONTINUE
            END

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
            ...    '${add_result}' in ['COURIER_ADDED', 'COURIER_ADDED_UNVERIFIED', 'ALREADY_BOOKED']
            IF    ${booking_ok}
                ${robotlog_write}=    giriton_auto_booking.Log Success Robotlog Write
                ...    ${candidate}
                ...    ${add_result}
                Log To Console    ROBOTLOG_WRITE=${robotlog_write}
                Log Auto Booking Step
                ...    ${candidate}
                ...    STEP_ROBOTLOG_WRITE_DONE
                ...    Google Sheet ROBOTLOG iras eredmenye: ${robotlog_write}
            END
            IF    not ${booking_ok}
                Log To Console    AUTO_BOOK_RESULT=${add_result} LOG=${log_result}
                CONTINUE
            END
        ELSE
            ${not_found_screenshot}=    giriton_auto_booking.Build Screenshot Name
            ...    ${candidate}
            ...    shift_not_found
            Capture Page Screenshot    ${not_found_screenshot}

            ${shift_not_empty}=    Evaluate    str("""${result}""").startswith("SHIFT_NOT_EMPTY")
            ${final_status}=    Set Variable If
            ...    ${shift_not_empty}
            ...    SHIFT_NOT_EMPTY
            ...    SHIFT_NOT_FOUND
            ${final_message}=    Set Variable If
            ...    ${shift_not_empty}
            ...    Megtalaltam a muszakot, de nincs nyitott kapacitas rajta, ezert nem foglalok. Robot eredmeny: ${result}. Screenshot: ${loaded_screenshot}, ${not_found_screenshot}
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
    ...    const inputs=Array.from(document.querySelectorAll('input.v-datefield-textfield, input[class*="v-datefield-textfield"], input[class*="date"], input[placeholder*="/"], input[aria-label*="date" i], input[title*="date" i], input[type="text"]')).filter(visible);
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
        ...    const exactTimes=baseMinutes === null ? [start] : (function(){const padded=toTime(baseMinutes,true); const plain=toTime(baseMinutes,false); return padded === plain ? [plain] : [padded, plain];})();
        ...    const variantFor=function(time){return [warehouse + '_' + time + ':', warehouse + '_' + time + '-', warehouse + '_' + time + ':1k', time + ':1k', time + ':', time + ' -', time + '-'].map(normalize);};
        ...    const capacityPairs=function(value){const compact=String(value || '').replaceAll(' ',''); const pairs=[]; for(let i=0;i<compact.length;i++){if(compact[i] !== '/'){continue;} let left=''; for(let j=i-1;j>=0 && compact[j]>='0' && compact[j]<='9';j--){left=compact[j]+left;} let right=''; for(let j=i+1;j<compact.length && compact[j]>='0' && compact[j]<='9';j++){right+=compact[j];} if(left && right){pairs.push([parseInt(left,10), parseInt(right,10)]);}} return pairs;};
        ...    const hasOpenCapacity=function(value){return capacityPairs(value).some(function(pair){return pair[1] > pair[0];});};
        ...    const capacityDebug=function(value){return capacityPairs(value).map(function(pair){return pair[0] + '/' + pair[1];}).join(',') || 'NO_CAPACITY_PAIR';};
        ...    const titles=[...document.querySelectorAll('div.panel-title')];
        ...    const scanTimes=exactTimes;
        ...    for(const title of titles){
        ...      const titleText=normalize(title.innerText || '');
        ...      if(!scanTimes.some(function(time){return variantFor(time).some(item => item && titleText.includes(item));})){continue;}
        ...      let card=null;
        ...      let fallbackCard=null;
        ...      for(let node=title.parentElement, depth=0; node && depth<10; depth++, node=node.parentElement){
        ...        const text=normalize(node.innerText || '');
        ...        const panelCount=node.querySelectorAll ? node.querySelectorAll('div.panel-title').length : 0;
        ...        if(text.includes(warehouse) && panelCount <= 1){
        ...          fallbackCard = fallbackCard || node;
        ...          if(capacityPairs(text).length > 0 || text.includes('Subscribed users')){card=node; break;}
        ...        }
        ...      }
        ...      card = card || fallbackCard;
        ...      if(!card){continue;}
        ...      const text=normalize(card.innerText || '');
        ...      const matchedTime=scanTimes.find(function(time){return titleText.includes(time + ':1k') || titleText.includes(time + ':') || titleText.includes(time + ' -') || titleText.includes(time + '-');}) || start;
        ...      const compactText=text.replaceAll(' ', '');
        ...      if(!hasOpenCapacity(compactText)){title.scrollIntoView({block:'center', inline:'nearest'}); return 'SHIFT_NOT_EMPTY capacity=' + capacityDebug(compactText) + ' title=' + titleText.slice(0,80);}
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

        IF    $result != 'CONTINUE'
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
    ${shift_start}=     Set Variable    ${candidate}[shift_start]
    ${warehouse}=       Set Variable    ${candidate}[warehouse]

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
    ...    STEP_POPUP_SHIFT_VERIFY_START
    ...    Popup muszak ellenorzese indul: ${shift_start}

    ${popup_shift_result}=    Verify Giriton Popup Shift
    ...    ${shift_start}

    IF    $popup_shift_result != 'OK'
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_POPUP_SHIFT_VERIFY_FAILED
        ...    Rossz muszak popup nyilt meg: ${popup_shift_result}
        Close Giriton Popup
        RETURN    WRONG_SHIFT_POPUP
    END

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_POPUP_SHIFT_VERIFY_DONE
    ...    Popup muszak ellenorzes rendben.

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_SUBSCRIBED_TAB_START
    ...    Subscribed users ful megnyitasa indul.

    ${selenium_tab_clicked}=    Run Keyword And Return Status
    ...    Click Element
    ...    xpath=(//div[contains(@class,'v-window')]//*[normalize-space(.)='Subscribed users (0)' or starts-with(normalize-space(.), 'Subscribed users')])[last()]
    ${tab_result}=    Set Variable If    ${selenium_tab_clicked}    OK    NOT_FOUND

    IF    $tab_result != 'OK'
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

    IF    $tab_result != 'OK'
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

    IF    $tab_open != 'YES'
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
    ...    const cleanCourierId=courierId.replace(/\.0$/, '');
    ...    const userNumber=cleanCourierId ? 'D' + cleanCourierId : '';
    ...    const normalize=value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    ...    const windows=[...document.querySelectorAll('.v-window')];
    ...    const win=windows[windows.length - 1] || document;
    ...    const text=win.innerText || '';
    ...    if(userNumber && text.includes(userNumber)){return 'YES';}
    ...    if(courierName && normalize(text).includes(normalize(courierName))){return 'YES';}
    ...    return 'NO';
    ...    ARGUMENTS
    ...    ${courier_id}
    ...    ${courier_name}

    IF    $already_added == 'YES'
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

    IF    $plus_result != 'OK'
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

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_ORG_SELECT_START
    ...    Futar szervezeti/raktar ag kivalasztasa indul: ${warehouse}

    ${org_select_result}=    Execute Javascript
    ...    try {
    ...      const warehouse=String(arguments[0] || '').trim().toUpperCase();
    ...      const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...      const cleanText=el => String((el && el.innerText) || '').trim().split(' ').filter(Boolean).join(' ');
    ...      const clickReal=function(el){
    ...        if(!el){return;}
    ...        el.scrollIntoView({block:'center', inline:'nearest'});
    ...        const rect=el.getBoundingClientRect();
    ...        const x=Math.max(0, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
    ...        const y=Math.max(0, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
    ...        const real=document.elementFromPoint(x, y) || el;
    ...        if(!real || !real.dispatchEvent){return;}
    ...        ['mouseover','mousemove','mousedown','mouseup','click','dblclick'].forEach(function(type){
    ...          real.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y}));
    ...        });
    ...      };
    ...      const dialogs=[...document.querySelectorAll('.v-window')].filter(visible);
    ...      const dialog=dialogs[dialogs.length - 1] || document;
    ...      const rows=[...dialog.querySelectorAll('tr.v-grid-row, tr[role="row"], .v-grid-row')].filter(visible);
    ...      const target=warehouse === 'BUD2' ? 'Just in Time Kft. - BUD2' : 'Just in Time Kft. - DSP';
    ...      const row=rows.find(item => cleanText(item).includes(target));
    ...      if(!row){const sample=rows.slice(0,8).map(item => cleanText(item).slice(0,120)).join(' | '); return 'NOT_FOUND warehouse=' + warehouse + ' rows=' + rows.length + ' sample=' + sample;}
    ...      clickReal(row);
    ...      return 'OK ' + cleanText(row).slice(0,160);
    ...    } catch(error) {
    ...      return 'JS_ERROR ' + (error && error.message ? error.message : String(error));
    ...    }
    ...    ARGUMENTS
    ...    ${warehouse}

    ${org_select_console}=    Evaluate    str($org_select_result).replace(chr(10), " ")[:900]
    Log To Console    AUTO_BOOK_COURIER_ORG_SELECT_RESULT=${org_select_console}
    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_ORG_SELECT_DONE
    ...    Futar szervezeti/raktar ag kivalasztas eredmenye: ${org_select_result}

    Sleep    2s

    Click Element
    ...    xpath=//*[@id="SearchField-tfTextSearch"]

    Press Keys
    ...    xpath=//*[@id="SearchField-tfTextSearch"]
    ...    CTRL+A
    Press Keys
    ...    xpath=//*[@id="SearchField-tfTextSearch"]
    ...    DELETE

    ${search_text}=    Set Variable If    '${courier_name}' != ''    ${courier_name}    ${email}

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_SEARCH_INPUT_START
    ...    Futar keresesi szoveg beirasa indul: ${search_text}

    Input Text
    ...    xpath=//*[@id="SearchField-tfTextSearch"]
    ...    ${search_text}

    Press Keys
    ...    xpath=//*[@id="SearchField-tfTextSearch"]
    ...    ENTER

    Execute Javascript
    ...    const field=document.querySelector('#SearchField-tfTextSearch');
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    if(field){
    ...      field.focus();
    ...      field.value=String(arguments[0] || '');
    ...      ['input','change','keyup'].forEach(type => field.dispatchEvent(new Event(type,{bubbles:true})));
    ...      field.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,cancelable:true,key:'Enter',code:'Enter',keyCode:13,which:13}));
    ...      field.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,cancelable:true,key:'Enter',code:'Enter',keyCode:13,which:13}));
    ...      const buttons=[...document.querySelectorAll('.v-window .v-button, .v-window button, .v-window [role="button"]')].filter(visible);
    ...      let searchButton=buttons.find(button => {
    ...        const text=String(button.innerText || button.getAttribute('aria-label') || button.title || button.className || '').toLowerCase();
    ...        return text.includes('search') || text.includes('keres') || text.includes('magnifier') || text.includes('find');
    ...      });
    ...      if(!searchButton){
    ...        const container=field.closest('.v-filterselect, .v-customcomponent, .v-widget, .v-slot') || field.parentElement;
    ...        searchButton=[...(container ? container.querySelectorAll('.v-button, button, [role="button"]') : [])].filter(visible).find(button => button !== field && button.offsetWidth <= 70 && button.offsetHeight <= 70);
    ...      }
    ...      if(searchButton){searchButton.click();}
    ...      field.blur();
    ...    }
    ...    ARGUMENTS
    ...    ${search_text}

    Sleep    4s

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_COURIER_SELECT_START
    ...    Futar sor keresese es kivalasztasa indul.

    ${select_result}=    Execute Javascript
    ...    try {
    ...      const courierId=String(arguments[0] || '').trim().replace(/\\.0$/, '');
    ...      const courierName=String(arguments[1] || '').trim().toLowerCase();
    ...      const email=String(arguments[2] || '').trim().toLowerCase();
    ...      const userNumber=courierId ? 'D' + courierId : '';
    ...      const fold=function(value){try{return String(value || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');}catch(error){return String(value || '');}};
    ...      const normalize=value => fold(value).toLowerCase().trim().split(' ').filter(Boolean).join(' ');
    ...      const nameParts=courierName.split(' ').filter(Boolean);
    ...      const reversedName=nameParts.length > 1 ? nameParts.slice(1).join(' ') + ' ' + nameParts[0] : courierName;
    ...      const foldedCourierName=normalize(courierName);
    ...      const foldedReversedName=normalize(reversedName);
    ...      const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...      const cleanText=el => String((el && el.innerText) || '').trim().split(' ').filter(Boolean).join(' ');
    ...      const clickReal=function(el){
    ...        if(!el){return;}
    ...        el.scrollIntoView({block:'center', inline:'nearest'});
    ...        const rect=el.getBoundingClientRect();
    ...        const x=Math.max(0, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
    ...        const y=Math.max(0, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
    ...        const real=document.elementFromPoint(x, y) || el;
    ...        if(!real || !real.dispatchEvent){return;}
    ...        ['mouseover','mousemove','mousedown','mouseup','click'].forEach(function(type){
    ...          real.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y}));
    ...        });
    ...      };
    ...      const dialogs=[...document.querySelectorAll('.v-window')].filter(visible);
    ...      const dialog=dialogs[dialogs.length - 1] || document;
    ...      let rows=[...dialog.querySelectorAll('tr.v-grid-row, tr[role="row"], .v-grid-row')].filter(visible);
    ...      if(rows.length === 0){rows=[...document.querySelectorAll('tr.v-grid-row, tr[role="row"], .v-grid-row')].filter(visible);}
    ...      const row=rows.find(item => {
    ...        const text=cleanText(item);
    ...        const lower=text.toLowerCase();
    ...        const folded=normalize(text);
    ...        if(userNumber && text.includes(userNumber)){return true;}
    ...        if(courierName && lower.includes(courierName)){return true;}
    ...        if(reversedName && lower.includes(reversedName)){return true;}
    ...        if(email && lower.includes(email)){return true;}
    ...        if(foldedCourierName && folded.includes(foldedCourierName)){return true;}
    ...        if(foldedReversedName && folded.includes(foldedReversedName)){return true;}
    ...        if(courierId && text.includes(courierId)){return true;}
    ...        return false;
    ...      });
    ...      if(!row){const sample=rows.slice(0,5).map(item => cleanText(item).slice(0,120)).join(' | '); return 'NOT_FOUND rows=' + rows.length + ' sample=' + sample;}
    ...      const checkbox=row.querySelector('input[type="checkbox"]');
    ...      const firstCell=row.querySelector('td, .v-grid-cell');
    ...      const vaadinCheck=row.querySelector('.v-checkbox, .v-grid-selection-checkbox, [class*="checkbox"], [class*="check"]');
    ...      [checkbox, vaadinCheck, firstCell, row].filter(Boolean).forEach(clickReal);
    ...      const selectedText=String((dialog.innerText || document.body.innerText) || '').toLowerCase();
    ...      const selected=String(row.className || '').includes('selected') || row.getAttribute('aria-selected') === 'true' || (checkbox && checkbox.checked) || !selectedText.includes('no record selected');
    ...      return selected ? 'OK' : 'NOT_SELECTED row=' + cleanText(row).slice(0,120);
    ...    } catch(error) {
    ...      return 'JS_ERROR ' + (error && error.message ? error.message : String(error));
    ...    }
    ...    ARGUMENTS
    ...    ${courier_id}
    ...    ${courier_name}
    ...    ${email}

    ${select_result_console}=    Evaluate    str($select_result).replace(chr(10), " ")[:900]
    Log To Console    AUTO_BOOK_COURIER_SELECT_RESULT=${select_result_console}

    IF    $select_result != 'OK'
        ${select_failed_screenshot}=    giriton_auto_booking.Build Screenshot Name
        ...    ${candidate}
        ...    courier_select_failed
        Capture Page Screenshot    ${select_failed_screenshot}
        Log Auto Booking Step
        ...    ${candidate}
        ...    STEP_COURIER_SELECT_FAILED
        ...    Futar sor nem talalhato vagy nincs tenylegesen kijelolve: ${select_result}. Screenshot: ${select_failed_screenshot}
        RETURN    COURIER_NOT_SELECTED
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
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    const dialogs=[...document.querySelectorAll('.v-window')].filter(visible);
    ...    const dialog=dialogs[dialogs.length - 1] || document;
    ...    if(String(dialog.innerText || '').toLowerCase().includes('no record selected')){return 'NO_RECORD_SELECTED';}
    ...    const button=document.querySelector('#SelectionDialog-btn-confirm-selection') || [...document.querySelectorAll('.v-button')].find(el => (el.innerText || '').includes('Choose') && visible(el));
    ...    if(!button){return 'NOT_FOUND';}
    ...    button.click();
    ...    return 'OK';

    IF    $choose_result != 'OK'
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
    ...    const cleanCourierId=courierId.replace(/\.0$/, '');
    ...    const userNumber=cleanCourierId ? 'D' + cleanCourierId : '';
    ...    const normalize=value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    const windows=[...document.querySelectorAll('.v-window')].filter(visible);
    ...    const win=windows[windows.length - 1] || document;
    ...    if((win.innerText || '').includes('Choose one or more entries')){return 'SELECTION_DIALOG_STILL_OPEN';}
    ...    const text=(win.innerText || '').toLowerCase();
    ...    const raw=win.innerText || '';
    ...    const folded=normalize(raw);
    ...    if(text.includes('were subscribed for selected shifts') || text.includes('subscribed users (1)')){return 'COURIER_ADDED';}
    ...    if(userNumber && raw.includes(userNumber)){return 'COURIER_ADDED';}
    ...    if(courierName && folded.includes(normalize(courierName))){return 'COURIER_ADDED';}
    ...    const failureText=['no record selected','not subscribed','error','failed','hiba','sikertelen','nem siker'].some(item => text.includes(item));
    ...    if(failureText){return 'COURIER_SELECTED_NOT_VERIFIED';}
    ...    return 'COURIER_ADDED_UNVERIFIED';
    ...    ARGUMENTS
    ...    ${courier_id}
    ...    ${courier_name}

    Log Auto Booking Step
    ...    ${candidate}
    ...    STEP_VERIFY_DONE
    ...    Foglalas ellenorzes eredmenye: ${verify_result}

    RETURN    ${verify_result}


Verify Giriton Popup Shift
    [Arguments]    ${shift_start}
    ${result}=    Execute Javascript
    ...    const start=String(arguments[0] || '').trim();
    ...    const toMinutes=function(value){const parts=String(value || '').split(':'); if(parts.length<2){return null;} const h=parseInt(parts[0],10); const m=parseInt(parts[1],10); if(Number.isNaN(h) || Number.isNaN(m)){return null;} return h*60+m;};
    ...    const toTime=function(total, padHour){total=(total+1440)%1440; const h=Math.floor(total/60); const m=total%60; const hh=padHour && h<10 ? '0'+h : String(h); const mm=m<10 ? '0'+m : String(m); return hh + ':' + mm;};
    ...    const base=toMinutes(start);
    ...    const offsets=[0,-15,15,-30,30];
    ...    const allowed=base === null ? [start] : offsets.flatMap(function(offset){const minute=base+offset; const padded=toTime(minute,true); const plain=toTime(minute,false); return padded === plain ? [plain] : [padded, plain];});
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    const windows=[...document.querySelectorAll('.v-window')].filter(visible);
    ...    const win=windows[windows.length - 1];
    ...    if(!win){return 'NO_WINDOW';}
    ...    const field=[...win.querySelectorAll('input, .v-filterselect-input, .v-select-select, .v-label, div, span')].filter(visible).map(el => String(el.value || el.innerText || el.textContent || '').trim()).find(text => text.includes('körös') || text.includes('koros') || allowed.some(time => text.includes(time + ':1k') || text.includes(time + '-1') || text.includes(time + ' -')));
    ...    const text=field || String(win.innerText || '');
    ...    return allowed.some(time => text.includes(time + ':1k') || text.includes(time + '-1') || text.includes(time + ' -') || text.includes(time + '-')) ? 'OK' : 'POPUP_SHIFT_MISMATCH=' + text.slice(0,120);
    ...    ARGUMENTS
    ...    ${shift_start}
    RETURN    ${result}


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
