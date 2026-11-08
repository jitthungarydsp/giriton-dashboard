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


class GoogleForm:
    def __init__(self, driver, expected_email):
        self.driver=driver
        self.email=expected_email.lower().strip()
        if not self.email:raise ValueError('QUALITY_FORM_GOOGLE_ACCOUNT szükséges: az engedélyezett beküldő Google-fiók e-mail-címe.')

    def open(self):
        from selenium.webdriver.common.by import By
        self.driver.get(form.FORM_URL)
        accounts=self.driver.find_elements(By.CSS_SELECTOR,'[data-user-email-address]')
        if not any((el.get_attribute('data-user-email-address') or '').lower()==self.email for el in accounts):
            raise LoginRequired('A kijelölt Google-fiókkal újra be kell jelentkezni a --login módban.')
        if not self.driver.find_elements(By.CSS_SELECTOR,'form[action*="/formResponse"]'):
            raise ValueError('Az űrlap nem elérhető.')

    def question(self, item):
        from selenium.webdriver.common.by import By
        nodes=self.driver.find_elements(By.CSS_SELECTOR,f'[data-params^="%.@.[{item},"]')
        if len(nodes)!=1:raise ValueError('A Google-űrlap mezői megváltoztak; új ellenőrzés szükséges.')
        return nodes[0].find_element(By.XPATH,'./ancestor::*[@role="listitem"][1]')

    def fill(self, payload):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        self.open()
        partner=self.question(930951024)
        partner.find_element(By.CSS_SELECTOR,'[role="listbox"]').click()
        choice=partner.find_element(By.XPATH,'.//*[@role="option" and @data-value="Just in Time Kft."]')
        WebDriverWait(self.driver,10).until(lambda _:choice.is_displayed());choice.click()
        category,fields=form.answers(payload)
        self.question(702410668).find_element(By.XPATH,f'.//*[@role="radio" and @data-value={json.dumps(category,ensure_ascii=False)}]').click()
        # Consent to record the selected account's email, if this form requests it.
        for checkbox in self.driver.find_elements(By.CSS_SELECTOR,'[role="checkbox"]'):
            if checkbox.is_displayed() and checkbox.get_attribute('aria-checked')=='false':checkbox.click()
        next_button=self.driver.find_elements(By.XPATH,'//*[@role="button"][.//*[normalize-space()="Következő" or normalize-space()="Next"]]')
        if len(next_button)!=1:raise ValueError('Nem található az űrlap Következő gombja.')
        next_button[0].click()
        WebDriverWait(self.driver,20).until(lambda _:self.driver.find_elements(By.CSS_SELECTOR,f'[data-params^="%.@.[{next(iter(fields))},"]') or 'accounts.google.com' in self.driver.current_url)
        if 'accounts.google.com' in self.driver.current_url:raise LoginRequired()
        for item,value in fields.items():
            question=self.question(item)
            inputs=question.find_elements(By.CSS_SELECTOR,'input[type="text"],textarea')
            if len(inputs)!=1:raise ValueError('Nem egyértelmű az űrlap szöveges mezője.')
            inputs[0].clear();inputs[0].send_keys(value)
        buttons=self.driver.find_elements(By.XPATH,'//*[@role="button"][.//*[normalize-space()="Küldés" or normalize-space()="Submit"]]')
        if len(buttons)!=1:raise ValueError('Nem található egyértelmű beküldési gomb.')
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
        subprocess.Popen([binary,'--user-data-dir='+str(profile),'--new-window',form.FORM_URL])
        print('Jelentkezz be a kijelölt Google-fiókkal. Ezután zárd be a robot összes Chrome-ablakát, és futtasd a --check parancsot. Ne küldj be tesztpanaszt az éles űrlapon.')
        return
    if args.check or args.dry_run:
        driver=browser(profile,visible=args.visible or bool(args.dry_run))
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
        sys.exit(1)
