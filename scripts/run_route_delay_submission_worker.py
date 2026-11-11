"""Submit explicitly queued devtest route complaints, one at a time.

Uses the dedicated GoogleFormRobot Chrome profile. No automatic retry after
claiming a job: interrupted/uncertain submissions require manual verification.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

worker=load('route_google_worker','scripts/run_quality_form_worker.py')
service=load('route_submission_drafts','resources/route_delay_form_drafts.py')


def process_record(record, save, make_page):
    if record['state']!='queued':
        return record
    claimed={**record,'state':'processing','updated_at':datetime.now(timezone.utc).isoformat()}
    save(record,claimed)  # Atomic durable claim BEFORE opening/clicking anything.
    click_attempted=False
    current=claimed
    try:
        draft=service.preparation.prepare_row(record['data'],record['source_row'])
        if draft['warnings']:
            raise ValueError('A reklamáció ellenőrzése hiányos.')
        page=make_page()
        button=page.fill(draft['payload'])
        # Journal immediately before the one permitted click. Any interruption
        # after this point keeps the record locked; never click it twice.
        click_attempted=True
        button.click()
        proof=page.wait_for_confirmation()
        if not proof:
            raise ValueError('A Google visszaigazolása nem látható.')
        current={**claimed,'state':'sent','confirmation':str(proof),
                 'submitted_at':datetime.now(timezone.utc).isoformat(),
                 'updated_at':datetime.now(timezone.utc).isoformat()}
        save(claimed,current)
        return current
    except Exception as exc:
        # If the success write lost its acknowledgement, a second CAS cannot
        # overwrite an already-sent DB row. The UI reloads the authoritative row.
        failed={**claimed,'state':'uncertain',
                'confirmation':('Beküldés eredménye ellenőrizendő: ' if click_attempted else 'Beküldés előtt megállt: ')+type(exc).__name__,
                'updated_at':datetime.now(timezone.utc).isoformat()}
        save(claimed,failed)
        return failed


class SubmissionPage(worker.GoogleForm):
    def wait_for_confirmation(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        def confirmed(driver):
            # This DOM marker is the Google Forms response receipt, not the
            # /formResponse URL, which is also used between form sections.
            for node in driver.find_elements(By.CSS_SELECTOR,'.vHW8K'):
                text=node.text.strip()
                if node.is_displayed() and any(phrase in text.casefold() for phrase in (
                    'válaszát rögzítettük','válaszodat rögzítettük','your response has been recorded')):
                    return text
            return False
        receipt=WebDriverWait(self.driver,30).until(confirmed)
        return f'Google Forms: {receipt} | {datetime.now(timezone.utc).isoformat()}'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--once',action='store_true')
    mode.add_argument('--watch',action='store_true')
    args=parser.parse_args()
    get=worker.settings()
    from supabase import create_client
    db=create_client(str(get('SUPABASE_URL')),str(get('SUPABASE_SERVICE_ROLE_KEY')))
    profile=worker.profile_path(get('QUALITY_FORM_PROFILE_DIR'))
    account=str(get('QUALITY_FORM_GOOGLE_ACCOUNT')or'system@jitt.hu')
    while True:
        blocked=(db.schema('settlement').table(service.TABLE).select('id')
                 .in_('state',['processing','uncertain']).limit(1).execute().data or [])
        if blocked:
            print('Korábbi beküldés eredménye ellenőrizendő. A robot nem folytatja a sort.',flush=True)
            return
        rows=(db.schema('settlement').table(service.TABLE).select('*').eq('state','queued')
              .order('updated_at').limit(1).execute().data or [])
        if rows:
            driver=None
            def make_page():
                nonlocal driver
                driver=worker.browser(profile,visible=True)
                return SubmissionPage(driver,account)
            try:
                result=process_record(rows[0],lambda previous,replacement:service.store_edit(db,previous,replacement),make_page)
                print('Reklamáció:',result['id'],result['state'],flush=True)
                if result['state']!='sent':
                    print('A robot megállt. Ellenőrizd az űrlapot és a Google-visszaigazolást.',flush=True)
                    return
            except Exception:
                print('A robot megállt. A mentett állapotot ellenőrizni kell; nincs automatikus újrabeküldés.',flush=True)
                return
            finally:
                if driver:
                    try:driver.quit()
                    except Exception:pass
        if not args.watch:
            return
        time.sleep(3)


if __name__=='__main__':
    main()
