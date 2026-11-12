"""Persistent-profile Google Forms worker. Run --login first; never exports Google cookies.
Fill-only worker: it NEVER clicks Submit. --once/--watch require admin approval in DB.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('quality_form_forwarding', ROOT/'resources/quality_form_forwarding.py')
form = importlib.util.module_from_spec(spec)
spec.loader.exec_module(form)


def settings():
    values = {}
    secrets = ROOT/'.streamlit/secrets.toml'
    if secrets.exists():
        import tomllib
        with secrets.open('rb') as handle:
            values = tomllib.load(handle)
    return lambda name: os.environ.get(name) or values.get(name, '')


class Database:
    def __init__(self, get):
        self.url = str(get('SUPABASE_URL')).rstrip('/')
        self.key = str(get('SUPABASE_SERVICE_ROLE_KEY'))
        if not self.url.startswith('https://') or not self.key:
            raise ValueError('SUPABASE_URL és SUPABASE_SERVICE_ROLE_KEY szükséges.')

    def rpc(self, name, payload=None):
        request = urllib.request.Request(self.url+'/rest/v1/rpc/'+name,
            data=json.dumps(payload or {}).encode(), headers={'apikey':self.key,
            'Authorization':'Bearer '+self.key,'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


def profile_path(value):
    default = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')/'Jitt'/'GoogleFormRobot'
    path = Path(value or default).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('A Google-profilt a repón kívül kell tárolni.')
    path.mkdir(parents=True,exist_ok=True)
    if os.name != 'nt':
        path.chmod(0o700)
    return path


def chrome_binary():
    candidates = [shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome')]
    for variable in ['PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA']:
        if os.environ.get(variable):
            candidates.append(str(Path(os.environ[variable])/'Google/Chrome/Application/chrome.exe'))
    return next((x for x in candidates if x and Path(x).is_file()),None)


def browser(profile, visible=False):
    from selenium import webdriver
    options=webdriver.ChromeOptions()
    options.add_argument('--user-data-dir='+str(profile))
    options.add_argument('--lang=hu-HU')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1100,1000')
    if not visible:
        options.add_argument('--headless=new')
    binary=chrome_binary()
    if binary:options.binary_location=binary
    driver=webdriver.Chrome(options=options)
    driver.set_page_load_timeout(50)
    return driver


class LoginRequired(Exception):
    pass


class FormInteractionError(Exception):
    """A named UI step failed before Submit; safe to display without form data."""


class GoogleForm:
    def __init__(self, driver, expected_email):
        self.driver=driver
        self.email=expected_email.lower().strip()
        if not self.email:raise ValueError('QUALITY_FORM_GOOGLE_ACCOUNT szükséges: az engedélyezett beküldő Google-fiók e-mail-címe.')

    def open(self, url=None):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        self.driver.get(url or form.FORM_URL)
        WebDriverWait(self.driver,20).until(lambda d: d.find_elements(By.TAG_NAME,'body'))
        accounts=self.driver.find_elements(By.CSS_SELECTOR,'[data-user-email-address]')
        matching=any((el.get_attribute('data-user-email-address') or '').lower()==self.email for el in accounts)
        # Google Forms also renders the selected account as visible header text.
        # Some versions omit data-user-email-address entirely.
        if not matching:
            import re
            body=self.driver.find_element(By.TAG_NAME,'body').text
            visible_emails=re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',body)
            matching=self.email in {value.lower()for value in visible_emails}
        if not matching:
            raise LoginRequired('A robothoz szükséges Google-fiók: '+self.email+
                                '. Futtasd: GoogleRobot.bat login, jelentkezz be ezzel a fiókkal, '
                                'zárd be az ablakát, majd GoogleRobot.bat check-login. A beküldés nem indult el.')
        if not self.driver.find_elements(By.CSS_SELECTOR,'form[action*="/formResponse"]'):
            raise ValueError('Az űrlap nem elérhető.')
        self.dismiss_draft_dialog()

    def dismiss_draft_dialog(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        for dialog in self.driver.find_elements(By.CSS_SELECTOR,'[role="dialog"], [role="alertdialog"]'):
            if not dialog.is_displayed():
                continue
            text=dialog.text
            if not isinstance(text,str):
                continue
            normalized=' '.join(text.casefold().split())
            if not any(title in normalized for title in (
                    'a jelenlegi piszkozatot folytatja', 'continue with your current draft')):
                continue
            buttons=[node for node in dialog.find_elements(By.CSS_SELECTOR,'[role="button"],button')
                     if node.is_displayed() and node.text.strip().casefold() in {'folytatás','continue'}]
            if len(buttons)!=1:
                # Forms can put the action footer outside the element carrying
                # role=dialog, or nest multiple button wrappers. Click the one
                # visible, innermost exact label after recognizing this prompt.
                label='normalize-space(.)="Folytatás" or normalize-space(.)="Continue"'
                buttons=[node for node in self.driver.find_elements(By.XPATH,
                         f'//*[{label}][not(.//*[{label}])]') if node.is_displayed()]
            if len(buttons)!=1:
                raise FormInteractionError('Piszkozatablak: nem azonosítható egyértelmű Folytatás gomb.')
            # Keep the current prefilled complaint; never restore another route's draft.
            self.click_control(buttons[0],'Jelenlegi piszkozat folytatása',dismiss_draft=False)
            WebDriverWait(self.driver,10).until(EC.invisibility_of_element(dialog))

    def question(self, item):
        from selenium.webdriver.common.by import By
        nodes=self.driver.find_elements(By.CSS_SELECTOR,f'[data-params^="%.@.[{item},"]')
        if len(nodes)!=1:raise ValueError('A Google-űrlap mezői megváltoztak; új ellenőrzés szükséges.')
        return nodes[0].find_element(By.XPATH,'./ancestor::*[@role="listitem"][1]')

    def wait_for_control(self, element, step, timeout=15, dismiss_draft=True):
        from selenium.webdriver.support.ui import WebDriverWait
        print('Űrlap lépés: '+step,flush=True)
        if dismiss_draft:
            self.dismiss_draft_dialog()
        # Scroll only; never bypass Google handlers with a JavaScript click.
        self.driver.execute_script(
            'arguments[0].scrollIntoView({block:"center",inline:"nearest"});',element)
        def uncovered(_):
            # Google may display the saved-draft prompt after the form loads.
            if dismiss_draft:
                self.dismiss_draft_dialog()
            return element.is_displayed() and element.is_enabled() and self.driver.execute_script('''
                const el=arguments[0], r=el.getBoundingClientRect();
                const x=(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2;
                const y=(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2;
                const top=document.elementFromPoint(x,y);
                return r.width>0 && r.height>0 && !!top && (top===el || el.contains(top));
            ''',element)
        try:
            WebDriverWait(self.driver,timeout).until(uncovered)
        except Exception as exc:
            raise FormInteractionError(step+': a vezérlő nem vált kattinthatóvá.') from exc

    def click_control(self, element, step, timeout=15, dismiss_draft=True):
        from selenium.common.exceptions import ElementClickInterceptedException
        # Only reversible selection/navigation controls use this helper.
        # Submit is always a separate, single click in the submission worker.
        for attempt in range(2):
            self.wait_for_control(element,step,timeout,dismiss_draft=dismiss_draft)
            try:
                element.click()
                return
            except ElementClickInterceptedException as exc:
                if attempt:
                    raise FormInteractionError(step+': egy másik elem takarja a vezérlőt.') from exc

    def ensure_email_consent(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        self.dismiss_draft_dialog()
        # Google can render either an ARIA checkbox or a native checkbox.
        boxes=[el for el in self.driver.find_elements(By.CSS_SELECTOR,
               '[role="checkbox"],input[type="checkbox"]') if el.is_displayed()]
        candidates=[]
        for box in boxes:
            label=' '.join([box.get_attribute('aria-label') or '',box.get_attribute('data-label') or ''])
            try:
                label+=' '+box.find_element(By.XPATH,'./ancestor::*[@role="listitem"][1]').text
            except Exception:
                pass
            if self.email in label.lower():
                candidates.append(box)
        if not candidates and len(boxes)==1:
            candidates=boxes
        if len(candidates)!=1:
            raise ValueError('Nem azonosítható egyértelműen az e-mail rögzítésének jelölőnégyzete.')
        box=candidates[0]
        def checked():
            return box.get_attribute('aria-checked')=='true' or box.is_selected()
        if not checked():
            self.click_control(box,'E-mail rögzítésének bejelölése')
        WebDriverWait(self.driver,10).until(lambda _:checked())

    def select_partner(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        label='Just in Time Kft.'
        partner=self.question(930951024)
        control=partner.find_element(By.CSS_SELECTOR,'[role="listbox"]')
        if control.text.strip()==label:
            return
        self.click_control(control,'Partnerlista megnyitása')
        def visible_option(_):
            # Google renders the expanded menu outside the question container;
            # a hidden duplicate may remain inside it. Select only visible items.
            options=[el for el in self.driver.find_elements(By.CSS_SELECTOR,
                     '[role="option"][data-value="Just in Time Kft."]')
                     if el.is_displayed() and el.is_enabled()]
            return options[0] if len(options)==1 else False
        choice=WebDriverWait(self.driver,15).until(visible_option)
        self.click_control(choice,'Just in Time Kft. kiválasztása')
        WebDriverWait(self.driver,10).until(lambda _:
            label in self.question(930951024).find_element(By.CSS_SELECTOR,'[role="listbox"]').text
            and not visible_option(None))

    def select_category(self, label):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        def option(_):
            nodes=[el for el in self.driver.find_elements(By.CSS_SELECTOR,'[role="radio"]')
                   if el.is_displayed() and (el.get_attribute('data-value')==label
                       or el.get_attribute('aria-label')==label)]
            return nodes[0] if len(nodes)==1 else False
        radio=WebDriverWait(self.driver,15).until(option)
        if radio.get_attribute('aria-checked')!='true':
            self.click_control(radio,'Reklamáció típusa: '+label)
        WebDriverWait(self.driver,10).until(lambda _:option(None)
            and option(None).get_attribute('aria-checked')=='true')

    def verify_fields(self, fields):
        from selenium.webdriver.common.by import By
        for item,value in fields.items():
            inputs=self.question(item).find_elements(By.CSS_SELECTOR,'input[type="text"],textarea')
            if len(inputs)!=1 or inputs[0].get_attribute('value')!=str(value):
                raise ValueError(f'A kötelező űrlapmező nem a várt adatot tartalmazza (mező: {item}).')

    def fill(self, payload):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        category,fields=form.answers(payload)
        # Prefill the verified public entry IDs for route complaints. UI checks
        # still verify category and every input; prefill alone never authorizes Submit.
        if payload['category']=='Túra alatti késés':
            prefill={'usp':'pp_url','entry.493012323':'Just in Time Kft.',
                     'entry.608543996':category,'entry.1629541155':payload['courier_id'],
                     'entry.139333198':payload['courier_name'],'entry.584723978':payload['route_id'],
                     'entry.1757898114':payload['description']}
            self.open(form.FORM_URL+'?'+urlencode(prefill))
        else:
            self.open()
        print('Űrlap: Google-fiók ellenőrizve.',flush=True)
        self.ensure_email_consent()
        print('Űrlap: e-mail rögzítése bejelölve.',flush=True)
        self.select_partner()
        print('Űrlap: Just in Time Kft. kiválasztva.',flush=True)
        self.select_category(category)
        print('Űrlap: reklamáció típusa ellenőrizve: '+category,flush=True)
        self.ensure_email_consent()
        next_button=self.driver.find_elements(By.XPATH,'//*[@role="button"][.//*[normalize-space()="Következő" or normalize-space()="Next"]]')
        if len(next_button)!=1:raise ValueError('Nem található az űrlap Következő gombja.')
        self.click_control(next_button[0],'Következő oldal megnyitása')
        WebDriverWait(self.driver,20).until(lambda _:self.driver.find_elements(By.CSS_SELECTOR,f'[data-params^="%.@.[{next(iter(fields))},"]') or 'accounts.google.com' in self.driver.current_url)
        if 'accounts.google.com' in self.driver.current_url:raise LoginRequired()
        for item,value in fields.items():
            question=self.question(item)
            inputs=question.find_elements(By.CSS_SELECTOR,'input[type="text"],textarea')
            if len(inputs)!=1:raise ValueError('Nem egyértelmű az űrlap szöveges mezője.')
            inputs[0].clear();inputs[0].send_keys(value)
        self.verify_fields(fields)
        print('Űrlap: minden kötelező mező kitöltve és visszaellenőrizve.',flush=True)
        buttons=self.driver.find_elements(By.XPATH,'//*[@role="button"][.//*[normalize-space()="Küldés" or normalize-space()="Submit"]]')
        if len(buttons)!=1:raise ValueError('Nem található egyértelmű beküldési gomb.')
        self.wait_for_control(buttons[0],'Küldés gomb előkészítése')
        return buttons[0]



def process_job(db,job,make_form):
    identity={'p_id':job['complaint_id'],'p_token':job['lease_token']}
    started=False
    try:
        # Journal the handoff before exposing an editable form. Expired leases must
        # never open a second copy while an administrator may still be submitting.
        journal=db.rpc('pwa_start_quality_submission',identity)
        if not journal:raise ValueError('A kitöltés előtti naplózás nem igazolható.')
        started=True
        page=make_form()
        page.fill(job['payload'])  # Deliberately ignore the Submit button.
        state='prepared'
    except LoginRequired:
        state='login_required'
    except Exception:
        state='uncertain' if started else 'failed'
    result=db.rpc('pwa_finish_quality_delivery',{**identity,'p_state':state,'p_confirmation':''})
    if not result:raise RuntimeError('A robot eredményének adatbázis-mentése nem igazolható.')
    return state


def wait_for_manual_close(driver):
    print('A form kitöltve. Ellenőrizd, majd TE kattints a Küldés gombra. '
          'Utána zárd be a robot ablakát. A továbbítást a PWA-ban külön rögzítsd.',flush=True)
    while True:
        try:
            if not driver.window_handles:return
        except Exception:
            return
        time.sleep(1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile')
    mode=parser.add_mutually_exclusive_group(required=True)
    for name in ['login','check','once','watch']:mode.add_argument('--'+name,action='store_true')
    mode.add_argument('--dry-run',metavar='PAYLOAD_JSON',help='Kitöltés helyi JSON-ból, beküldés és adatbázis-módosítás nélkül.')
    parser.add_argument('--visible',action='store_true')
    args=parser.parse_args();get=settings();profile=profile_path(args.profile or get('QUALITY_FORM_PROFILE_DIR'))
    account=str(get('QUALITY_FORM_GOOGLE_ACCOUNT') or 'system@jitt.hu')
    if args.login:
        binary=chrome_binary()
        if not binary:raise ValueError('Chrome nem található.')
        process=subprocess.Popen([binary,'--user-data-dir='+str(profile),'--new-window',form.FORM_URL])
        print('Chrome indítás kérve. Profil: '+str(profile)+' | folyamat: '+str(process.pid),flush=True)
        print('Jelentkezz be a kijelölt Google-fiókkal. Ezután zárd be a robot összes Chrome-ablakát, és futtasd a --check parancsot. Ne küldj be tesztpanaszt az éles űrlapon.')
        return
    if args.check or args.dry_run:
        # Login checks must not create an invisible profile-holding browser.
        driver=browser(profile,visible=args.check or args.visible or bool(args.dry_run))
        try:
            page=GoogleForm(driver,account)
            if args.dry_run:
                page.fill(json.loads(Path(args.dry_run).read_text(encoding='utf-8-sig')))
                print('Kitöltés kész. NEM történt beküldés.');input('Enter: a robotablak bezárása.')
            else:page.open();print('Google-bejelentkezés rendben. Nem történt beküldés.')
        finally:driver.quit()
        return
    db=Database(get)
    while True:
        jobs=db.rpc('pwa_claim_quality_delivery')
        if jobs:
            driver=None
            def make_form():
                nonlocal driver
                driver=browser(profile,visible=True)
                return GoogleForm(driver,account)
            try:
                state=process_job(db,jobs[0],make_form)
                print('Kitöltő robot:',state,flush=True)
                if state=='prepared':wait_for_manual_close(driver)
            finally:
                if driver:driver.quit()
        if not args.watch:break
        time.sleep(15)  # One small queue claim, never full-table synchronization.


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('A robot megállt. Hibatípus:',type(exc).__name__,file=sys.stderr)
        if isinstance(exc,LoginRequired):
            print(str(exc) or 'Google-bejelentkezés szükséges.',file=sys.stderr)
        if type(exc).__name__=='SessionNotCreatedException':
            print('A robot Chrome-profilja foglalt lehet, vagy a Chrome nem indult el. '
                  'Zárd be a GoogleFormRobot külön Chrome-ablakait. '
                  'Ha nem látszik ablak, a Feladatkezelőben csak a GoogleFormRobot '
                  'parancssorú chrome.exe folyamatot állítsd le. '
                  'Ezután: GoogleRobot.bat login, majd a robotablakok bezárása után '
                  'GoogleRobot.bat check-login. A szokásos Chrome-profilodat nem kell bezárni.',file=sys.stderr)
        sys.exit(1)
