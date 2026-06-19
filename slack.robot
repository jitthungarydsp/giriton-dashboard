*** Settings ***
Library    SeleniumLibrary


*** Variables ***



*** Test Cases ***
Slack login
    Open Browser
    ...    https://app.slack.com/client/E01R5ED1R0U/C0B6B3F5S31
    ...    chrome
    ...    executable_path=C:/Giriton/robots/Drivers/chromedriver

    Maximize Browser Window
    Sleep    10
    Input Text    locator=//*[@id="domain"]    text=rohlikgroup.enterprise
    Click Button    locator=//*[@id="page_contents"]/div/div/div[1]/div[2]/form/button
    Wait Until Element Is Visible    locator=//*[@id="enterprise_member_guest_account_signin_link"]    timeout=60s
    Click Element    locator=//*[@id="enterprise_member_guest_account_signin_link"]
    Input Text    locator=//*[@id="email"]    text=gurzobalazs@gmail.com
    Input Text    locator=//*[@id="password"]    text=Melinda18852Hunor@
    Click Button    locator=//*[@id="enterprise_signin_form"]/button
    Sleep    10
    Go To    url=https://app.slack.com/client/E01R5ED1R0U/C0AT0BN79B7
    Go To    url=https://app.slack.com/client/E01R5ED1R0U/C0B6B3F5S31