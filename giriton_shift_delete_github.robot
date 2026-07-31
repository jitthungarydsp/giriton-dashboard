*** Settings ***
Resource    resources/keywords_github.robot
Library    resources/giriton_auto_booking.py
Library    SeleniumLibrary
Library    DateTime
Library    String


*** Variables ***
${DELETE_SERIAL}
${DELETE_WORK_DATE}
${DELETE_WAREHOUSE}
${DELETE_SHIFT_START}
${DELETE_COURIER_ID}
${DELETE_COURIER_NAME}


*** Test Cases ***
Delete Giriton Shift Subscription
    ${candidate}=    Create Dictionary
    ...    serial=${DELETE_SERIAL}
    ...    work_date=${DELETE_WORK_DATE}
    ...    warehouse=${DELETE_WAREHOUSE}
    ...    shift_start=${DELETE_SHIFT_START}
    ...    courier_id=${DELETE_COURIER_ID}
    ...    courier_name=${DELETE_COURIER_NAME}

    Log Giriton Delete Step    ${candidate}    STEP_LOGIN_START    Giriton bejelentkezes indul.
    keywords_github.Bejelentkezes
    Log Giriton Delete Step    ${candidate}    STEP_LOGIN_DONE    Giriton bejelentkezes kesz.

    keywords_github.Click Shift Subs
    keywords_github.Select All Departments
    Sleep    5s

    ${giriton_date}=    Convert Date
    ...    ${DELETE_WORK_DATE}
    ...    result_format=%d/%m/%Y
    ...    date_format=%Y-%m-%d

    Beallit Giriton Datum Torleshez    ${giriton_date}

    ${result}=    Find Giriton Delete Shift Card
    ...    ${DELETE_WAREHOUSE}
    ...    ${DELETE_SHIFT_START}

    IF    '${result}' != 'FOUND_CLICKED'
        Log Giriton Delete Step
        ...    ${candidate}
        ...    STEP_SHIFT_NOT_FOUND
        ...    Nem talaltam torleshez megfelelo muszakkartyat: ${result}
        Fail    Nem talaltam torleshez megfelelo muszakkartyat: ${result}
    END

    Wait Until Keyword Succeeds
    ...    10x
    ...    1s
    ...    Giriton Delete Popup Should Be Open

    ${popup_shift}=    Verify Delete Popup Shift
    ...    ${DELETE_SHIFT_START}
    IF    '${popup_shift}' != 'OK'
        Close Giriton Delete Popup
        Fail    Rossz muszak popup nyilt meg torleshez: ${popup_shift}
    END

    ${delete_result}=    Delete Courier From Giriton Popup
    ...    ${DELETE_COURIER_ID}
    ...    ${DELETE_COURIER_NAME}

    Log Giriton Delete Step
    ...    ${candidate}
    ...    STEP_DELETE_DONE
    ...    Torles eredmenye: ${delete_result}

    IF    '${delete_result}' != 'COURIER_REMOVED'
        Close Giriton Delete Popup
        Fail    Giriton torles sikertelen: ${delete_result}
    END

    Close Giriton Delete Popup
    Log To Console    GIRITON_DELETE_RESULT=${delete_result}


*** Keywords ***
Log Giriton Delete Step
    [Arguments]    ${candidate}    ${status}    ${message}
    ${log_result}=    giriton_auto_booking.Log Giriton Booking Result
    ...    ${candidate}
    ...    ${status}
    ...    ${message}
    Log To Console    GIRITON_DELETE_STEP=${status} LOG=${log_result}


Beallit Giriton Datum Torleshez
    [Arguments]    ${datum_giriton}
    Execute Javascript
    ...    const input=[...document.querySelectorAll('input.v-datefield-textfield')].find(el => el.offsetWidth > 0 && el.offsetHeight > 0); if(!input){throw new Error('Visible date input not found');} input.focus(); input.value=arguments[0]; input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true})); input.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true})); input.blur();
    ...    ARGUMENTS
    ...    ${datum_giriton}
    Sleep    4s


Find Giriton Delete Shift Card
    [Arguments]    ${warehouse}    ${shift_start}
    Execute Javascript
    ...    let els=[...document.querySelectorAll('*')]; let scrollable=els.filter(e=>e.scrollHeight>e.clientHeight); let biggest=scrollable.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0]; if(biggest){biggest.scrollTop=0;}
    Sleep    1s
    FOR    ${i}    IN RANGE    25
        ${result}=    Execute Javascript
        ...    const warehouse=String(arguments[0] || '').trim().toUpperCase();
        ...    const start=String(arguments[1] || '').trim();
        ...    const normalize=value => String(value || '').trim().split(' ').filter(Boolean).join(' ');
        ...    const toMinutes=function(value){const parts=String(value || '').split(':'); if(parts.length<2){return null;} const h=parseInt(parts[0],10); const m=parseInt(parts[1],10); if(Number.isNaN(h) || Number.isNaN(m)){return null;} return h*60+m;};
        ...    const toTime=function(total, padHour){total=(total+1440)%1440; const h=Math.floor(total/60); const m=total%60; const hh=padHour && h<10 ? '0'+h : String(h); const mm=m<10 ? '0'+m : String(m); return hh + ':' + mm;};
        ...    const base=toMinutes(start);
        ...    const times=base === null ? [start] : (function(){const padded=toTime(base,true); const plain=toTime(base,false); return padded === plain ? [plain] : [padded, plain];})();
        ...    const variantFor=time => [warehouse + '_' + time, time + ':1k', time + ':', time + ' -', time + '-'].map(normalize);
        ...    const titles=[...document.querySelectorAll('div.panel-title')];
        ...    for(const title of titles){
        ...      const titleText=normalize(title.innerText || '');
        ...      if(!times.some(time => variantFor(time).some(item => item && titleText.includes(item)))){continue;}
        ...      let card=null;
        ...      for(let node=title, depth=0; node && depth<8; depth++, node=node.parentElement){
        ...        const text=normalize(node.innerText || '');
        ...        const panelCount=node.querySelectorAll ? node.querySelectorAll('div.panel-title').length : 0;
        ...        if(text.includes(warehouse) && panelCount <= 1){card=node; break;}
        ...      }
        ...      if(!card){continue;}
        ...      title.scrollIntoView({block:'center', inline:'nearest'});
        ...      const clickables=[title].concat(Array.from(card.querySelectorAll('.subscribed-persons-label, .v-label, .v-progressbar, .v-progressbar-wrapper, .v-progressbar-indicator, div, span')).filter(el => el.offsetWidth > 0 && el.offsetHeight > 0));
        ...      for(const clickable of clickables.slice(0,12)){
        ...        clickable.scrollIntoView({block:'center', inline:'nearest'});
        ...        ['mouseover','mousemove','mousedown','mouseup','click','dblclick'].forEach(type => clickable.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window})));
        ...        if(document.querySelector('.v-window')){return 'FOUND_CLICKED';}
        ...      }
        ...      return 'FOUND_CLICKED';
        ...    }
        ...    const scrollables=[...document.querySelectorAll('*')].filter(e=>e.scrollHeight>e.clientHeight);
        ...    const biggest=scrollables.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0];
        ...    if(biggest && biggest.scrollTop + biggest.clientHeight < biggest.scrollHeight - 5){biggest.scrollTop = biggest.scrollTop + Math.max(400, biggest.clientHeight * 0.85); return 'CONTINUE';}
        ...    return 'NOT_FOUND';
        ...    ARGUMENTS
        ...    ${warehouse}
        ...    ${shift_start}
        IF    '${result}' != 'CONTINUE'
            RETURN    ${result}
        END
        Sleep    1s
    END
    RETURN    NOT_FOUND


Giriton Delete Popup Should Be Open
    ${state}=    Execute Javascript
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0; const wins=[...document.querySelectorAll('.v-window')].filter(visible); const win=wins[wins.length-1]; if(!win){return 'NO';} const text=String(win.innerText || ''); return text.includes('Subscribed users') || text.includes('Shift subscription') ? 'YES' : 'NO';
    Should Be Equal As Strings    ${state}    YES


Verify Delete Popup Shift
    [Arguments]    ${shift_start}
    ${result}=    Execute Javascript
    ...    const start=String(arguments[0] || '').trim();
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    const wins=[...document.querySelectorAll('.v-window')].filter(visible);
    ...    const win=wins[wins.length-1];
    ...    if(!win){return 'NO_WINDOW';}
    ...    const text=[...win.querySelectorAll('input, div, span')].filter(visible).map(el => String(el.value || el.innerText || el.textContent || '')).join(' ');
    ...    return text.includes(start + ':1k') || text.includes(start + '-1') || text.includes(start + ' -') || text.includes(start + '-') ? 'OK' : 'MISMATCH=' + text.slice(0,100);
    ...    ARGUMENTS
    ...    ${shift_start}
    RETURN    ${result}


Delete Courier From Giriton Popup
    [Arguments]    ${courier_id}    ${courier_name}
    ${result}=    Execute Javascript
    ...    const courierId=String(arguments[0] || '').replace(/\.0$/, '').trim();
    ...    const courierName=String(arguments[1] || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
    ...    const visible=el => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
    ...    const normalize=value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    ...    const wins=[...document.querySelectorAll('.v-window')].filter(visible);
    ...    const win=wins[wins.length-1];
    ...    if(!win){return 'NO_WINDOW';}
    ...    const tab=[...win.querySelectorAll('*')].filter(visible).find(el => String(el.innerText || el.textContent || '').trim().startsWith('Subscribed users'));
    ...    if(tab){tab.click();}
    ...    const rows=[...win.querySelectorAll('tr.v-grid-row, tr[role="row"], tr')].filter(visible);
    ...    const row=rows.find(item => {const text=item.innerText || ''; const folded=normalize(text); return (courierId && text.includes('D' + courierId)) || (courierName && folded.includes(courierName));});
    ...    if(!row){return 'COURIER_NOT_IN_SHIFT';}
    ...    const remove=[...row.querySelectorAll('.v-button, button, [role="button"], span, div')].filter(visible).find(el => {const cls=String(el.className || '').toLowerCase(); const text=String(el.innerText || el.textContent || '').trim(); const style=getComputedStyle(el); return text === '-' || cls.includes('danger') || cls.includes('minus') || cls.includes('remove') || style.backgroundColor.includes('244, 67, 54') || style.backgroundColor.includes('229, 57, 53');});
    ...    if(!remove){return 'REMOVE_BUTTON_NOT_FOUND';}
    ...    remove.click();
    ...    return 'COURIER_REMOVED';
    ...    ARGUMENTS
    ...    ${courier_id}
    ...    ${courier_name}
    Sleep    2s
    RETURN    ${result}


Close Giriton Delete Popup
    Execute Javascript
    ...    const wins=[...document.querySelectorAll('.v-window')]; const win=wins[wins.length - 1]; if(win){const close=win.querySelector('.v-window-closebox'); if(close){close.click();}}
    Sleep    1s
