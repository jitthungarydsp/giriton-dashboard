*** Settings ***
Library    SeleniumLibrary
Library    chrome_options.py


*** Keywords ***
Bejelentkezes
    ${options}=    Create Github Chrome Options
    Open Browser    https://kiflihu.giriton.com/    chrome    options=${options}
    Set Window Size    1920    1080
    Wait Until Element Is Visible    locator=//*[@id="CompanyLoginPanel-tfUserLogin"]    timeout=30s
    SeleniumLibrary.Input Text    locator=//*[@id="CompanyLoginPanel-tfUserLogin"]    text=%{GIRITON_USER}
    SeleniumLibrary.Input Text    locator=//*[@id="CompanyLoginPanel-pfUserPassword"]    text=%{GIRITON_PASSWORD}
    Click Element    locator=//*[@id="ROOT-2521314"]/div/div[2]/div/div/div/div[3]/div/div[3]/div/div[1]/div


Click Shift Subs
    SeleniumLibrary.Wait Until Element Is Visible    locator=//*[@id="layMenuItems"]/div[5]/div/span    timeout=30s
    SeleniumLibrary.Click Element    locator=//*[@id="layMenuItems"]/div[5]/div/span


Click Attendance
    SeleniumLibrary.Wait Until Element Is Visible
    ...    xpath=//*[@id="layMenuItems"]/div[2]/div/span
    ...    timeout=30s
    SeleniumLibrary.Click Element
    ...    xpath=//*[@id="layMenuItems"]/div[2]/div/span


Select All Departments
    SeleniumLibrary.Wait Until Element Is Visible
    ...    xpath=//span[contains(@class,'v-button-caption') and (contains(normalize-space(.),'Just in Time Kft') or contains(normalize-space(.),'multiple departm') or contains(normalize-space(.),'all departments'))]
    ...    timeout=30s

    Execute Javascript
    ...    const departmentButton=[...document.querySelectorAll('.v-button')].find(el => { const text=(el.innerText || '').trim(); return (text.includes('Just in Time Kft') || text.includes('multiple departm') || text.includes('all departments')) && el.offsetWidth > 0 && el.offsetHeight > 0; }); if(departmentButton){departmentButton.click();} else {throw new Error('Visible department button not found');}

    SeleniumLibrary.Wait Until Page Contains
    ...    Departments
    ...    timeout=30s

    Execute Javascript
    ...    const label=[...document.querySelectorAll('label')].find(el => (el.innerText || '').includes('all departments') && el.offsetWidth > 0 && el.offsetHeight > 0); if(label){label.click();} else {throw new Error('Visible all departments label not found');}

    Sleep    1s

    Execute Javascript
    ...    const button=[...document.querySelectorAll('.v-button')].find(el => (el.innerText || '').trim() === 'Choose' && el.offsetWidth > 0 && el.offsetHeight > 0); if(button){button.click();} else {throw new Error('Visible Choose button not found');}

    Sleep    3s
