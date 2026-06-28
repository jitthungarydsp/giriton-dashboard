*** Settings ***
Library    SeleniumLibrary


*** Keywords ***
Bejelentkezes
    ${options}=    Evaluate    sys.modules['selenium.webdriver'].ChromeOptions()    sys, selenium.webdriver
    Call Method    ${options}    add_argument    --headless=new
    Call Method    ${options}    add_argument    --no-sandbox
    Call Method    ${options}    add_argument    --disable-dev-shm-usage
    Call Method    ${options}    add_argument    --disable-gpu
    Call Method    ${options}    add_argument    --window-size=1920,1080
    Open Browser    https://kiflihu.giriton.com/    chrome    options=${options}
    Set Window Size    1920    1080
    Wait Until Element Is Visible    locator=//*[@id="CompanyLoginPanel-tfUserLogin"]    timeout=30s
    SeleniumLibrary.Input Text    locator=//*[@id="CompanyLoginPanel-tfUserLogin"]    text=%{GIRITON_USER}
    SeleniumLibrary.Input Text    locator=//*[@id="CompanyLoginPanel-pfUserPassword"]    text=%{GIRITON_PASSWORD}
    Click Element    locator=//*[@id="ROOT-2521314"]/div/div[2]/div/div/div/div[3]/div/div[3]/div/div[1]/div


Click Shift Subs
    SeleniumLibrary.Wait Until Element Is Visible    locator=//*[@id="layMenuItems"]/div[5]/div/span    timeout=30s
    SeleniumLibrary.Click Element    locator=//*[@id="layMenuItems"]/div[5]/div/span
