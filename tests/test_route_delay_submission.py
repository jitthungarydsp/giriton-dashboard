import importlib.util
from pathlib import Path
from unittest.mock import Mock
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('route_sender',ROOT/'scripts/run_route_delay_submission_worker.py')
sender=importlib.util.module_from_spec(spec);spec.loader.exec_module(sender)
service=sender.service


class SubmissionTest(unittest.TestCase):
    def test_covered_control_is_never_clicked(self):
        driver=Mock();element=Mock();driver.execute_script.return_value=False
        page=sender.worker.GoogleForm(driver,'robot@example.com')
        with self.assertRaisesRegex(sender.worker.FormInteractionError,'Partnerlista'):
            page.click_control(element,'Partnerlista',timeout=0)
        element.click.assert_not_called()

    def test_selection_rewaits_after_interception(self):
        from selenium.common.exceptions import ElementClickInterceptedException
        driver=Mock();element=Mock()
        element.click.side_effect=[ElementClickInterceptedException(),None]
        page=sender.worker.GoogleForm(driver,'robot@example.com')
        page.wait_for_control=Mock()
        page.click_control(element,'Partnerlista')
        self.assertEqual(page.wait_for_control.call_count,2)
        self.assertEqual(element.click.call_count,2)

    def test_repeated_interception_reports_step_and_stops(self):
        from selenium.common.exceptions import ElementClickInterceptedException
        element=Mock();element.click.side_effect=ElementClickInterceptedException()
        page=sender.worker.GoogleForm(Mock(),'robot@example.com');page.wait_for_control=Mock()
        with self.assertRaisesRegex(sender.worker.FormInteractionError,'Reklamáció típusa'):
            page.click_control(element,'Reklamáció típusa')
        self.assertEqual(element.click.call_count,2)

    def test_category_must_be_checked_not_merely_present(self):
        driver=Mock();page=sender.worker.GoogleForm(driver,'robot@example.com');selected=[False]
        radio=Mock();radio.is_displayed.return_value=True
        label='Túra alatti késés / Route delay'
        radio.get_attribute.side_effect=lambda key:label if key=='data-value'else ('true'if selected[0]else'false')if key=='aria-checked'else''
        radio.click.side_effect=lambda:selected.__setitem__(0,True)
        driver.find_elements.return_value=[radio]
        page.select_category(label)
        self.assertTrue(selected[0]);radio.click.assert_called_once()
        page.select_category(label);radio.click.assert_called_once()

    def test_wrong_or_empty_field_prevents_submission(self):
        page=sender.worker.GoogleForm(Mock(),'robot@example.com');question=Mock();field=Mock()
        page.question=Mock(return_value=question);question.find_elements.return_value=[field]
        for value in ['', 'another courier']:
            field.get_attribute.return_value=value
            with self.assertRaises(ValueError):page.verify_fields({238065601:'6498'})
        field.get_attribute.return_value='6498'
        page.verify_fields({238065601:'6498'})

    def test_pre_submit_verification_failure_never_clicks_submit(self):
        page=self.page();page.verify_fields.side_effect=ValueError('field is empty')
        result=sender.process_record(self.record(),Mock(),lambda:page)
        self.assertEqual(result['state'],'uncertain')
        page.fill.return_value.click.assert_not_called()

    def test_intercepted_submit_is_never_retried(self):
        from selenium.common.exceptions import ElementClickInterceptedException
        page=self.page();page.fill.return_value.click.side_effect=ElementClickInterceptedException()
        result=sender.process_record(self.record(),Mock(),lambda:page)
        self.assertEqual(result['state'],'uncertain')
        page.fill.return_value.click.assert_called_once()
        page.wait_for_confirmation.assert_not_called()

    def test_partner_selection_uses_visible_menu_option_not_hidden_duplicate(self):
        driver=Mock();page=sender.worker.GoogleForm(driver,'robot@example.com')
        question=Mock();control=Mock();control.text='Kiválasztás'
        question.find_element.return_value=control;page.question=Mock(return_value=question)
        hidden=Mock();hidden.is_displayed.return_value=False
        visible=Mock();visible.is_displayed.return_value=True;visible.is_enabled.return_value=True
        def select():
            control.text='Just in Time Kft.'
            visible.is_displayed.return_value=False
        visible.click.side_effect=select
        driver.find_elements.return_value=[hidden,visible]
        page.select_partner()
        hidden.click.assert_not_called();visible.click.assert_called_once()
        control.click.assert_called_once()

    def test_selected_partner_is_not_toggled_again(self):
        driver=Mock();page=sender.worker.GoogleForm(driver,'robot@example.com')
        control=Mock();control.text='Just in Time Kft.'
        page.question=Mock();page.question.return_value.find_element.return_value=control
        page.select_partner()
        control.click.assert_not_called()
    def test_email_checkbox_is_clicked_and_verified_for_native_and_aria_controls(self):
        for native in [False,True]:
            driver=Mock();box=Mock();selected=[False]
            box.is_displayed.return_value=True
            box.find_element.return_value.text='Record robot@example.com email'
            box.is_selected.side_effect=lambda:selected[0] if native else False
            box.get_attribute.side_effect=lambda key: ('true' if selected[0] else 'false') if key=='aria-checked' and not native else None
            box.click.side_effect=lambda:selected.__setitem__(0,True)
            driver.find_elements.return_value=[box]
            sender.worker.GoogleForm(driver,'robot@example.com').ensure_email_consent()
            box.click.assert_called_once()
            sender.worker.GoogleForm(driver,'robot@example.com').ensure_email_consent()
            box.click.assert_called_once()

    def test_ambiguous_email_checkbox_never_checks_unrelated_boxes(self):
        driver=Mock();boxes=[Mock(),Mock()]
        for box in boxes:
            box.is_displayed.return_value=True;box.get_attribute.return_value=''
            box.find_element.return_value.text='Unrelated option'
        driver.find_elements.return_value=boxes
        with self.assertRaises(ValueError):sender.worker.GoogleForm(driver,'robot@example.com').ensure_email_consent()
        for box in boxes:box.click.assert_not_called()

    def record(self):
        data={'Dátum':'2026-10-01','Futár ID':'6498','Futár':'Abonyi György','Túra ID':'1557743',
              'Javasolt kategória száma':4,'Kategóriajavaslat':'Optimalizálatlan túra',
              'Adat / megfontolás':'4 cím','Kategória futárral egyeztetve':'Igen',
              'Reklamáció indoklása':'Egyeztetett indoklás'}
        record=service.make_record(data,2)
        return service.queue_record(service.prepare_record(record,'admin'),'admin')
    def page(self):
        page=Mock();page.wait_for_confirmation.return_value='Google Forms: Your response has been recorded.'
        return page
    def test_claim_before_one_click_then_confirm(self):
        row=self.record();events=[];page=self.page()
        page.fill.return_value.click.side_effect=lambda:events.append('click')
        result=sender.process_record(row,lambda a,b:events.append(b['state']),lambda:page)
        self.assertEqual(events,['processing','click','sent'])
        self.assertEqual(result['state'],'sent')
        page.fill.return_value.click.assert_called_once()
    def test_cas_failure_never_opens_or_clicks(self):
        factory=Mock()
        with self.assertRaises(ValueError):
            sender.process_record(self.record(),Mock(side_effect=ValueError('stale')),factory)
        factory.assert_not_called()
    def test_confirmation_timeout_locks_row_and_never_retries(self):
        page=self.page();page.wait_for_confirmation.side_effect=TimeoutError()
        result=sender.process_record(self.record(),Mock(),lambda:page)
        self.assertEqual(result['state'],'uncertain')
        page.fill.return_value.click.assert_called_once()
        factory=Mock()
        self.assertEqual(sender.process_record(result,Mock(),factory),result)
        factory.assert_not_called()
    def test_login_failure_locks_without_click(self):
        page=self.page();page.fill.side_effect=sender.worker.LoginRequired()
        result=sender.process_record(self.record(),Mock(),lambda:page)
        self.assertEqual(result['state'],'uncertain')
        page.wait_for_confirmation.assert_not_called()
    def test_save_ack_loss_never_clicks_twice(self):
        page=self.page();save=Mock(side_effect=[None,OSError('ack lost'),ValueError('already sent')])
        with self.assertRaises(ValueError):sender.process_record(self.record(),save,lambda:page)
        page.fill.return_value.click.assert_called_once()
    def test_import_edit_and_backup_do_not_unlock_pending_submission(self):
        row=self.record()
        with self.assertRaises(ValueError):service.edit_record(row,row['data'],'admin')
        with self.assertRaises(ValueError):service.prepare_record(row,'admin')
        import json
        self.assertEqual(service.read_backup(json.dumps([row]))[0]['state'],'uncertain')
        changed={**row,'state':'draft','content_hash':'changed'}
        merged,counts=service.merge_import([row],[changed],overwrite=True)
        self.assertEqual(merged,[row]);self.assertEqual(counts['updated'],0)
    def test_batch_queues_only_reviewed_and_passes_versions_to_rpc(self):
        queued=self.record();ready={**queued,'state':'prepared'}
        draft={**ready,'id':'draft','state':'draft'};sent={**ready,'id':'sent','state':'sent'}
        db=Mock();db.schema.return_value.rpc.return_value.execute.return_value.data=1
        self.assertEqual(service.queue_batch(db,[ready,draft,sent],'admin'),1)
        params=db.schema.return_value.rpc.call_args.args[1]
        self.assertEqual([r['id']for r in params['p_records']],[ready['id']])
        self.assertEqual(params['p_records'][0]['updated_at'],ready['updated_at'])
    def test_batch_failure_never_reports_success_and_pending_blocks_new_batch(self):
        row=self.record();db=Mock()
        with self.assertRaises(ValueError):service.queue_batch(db,[row],'admin')
        db.schema.assert_not_called()
        row['state']='prepared';db.schema.return_value.rpc.return_value.execute.return_value.data=0
        with self.assertRaises(ValueError):service.queue_batch(db,[row],'admin')
    def test_next_selection_skips_sent_and_pending_but_not_review(self):
        rows=[dict(id='a',state='sent'),dict(id='b',state='queued'),dict(id='c',state='draft')]
        self.assertEqual(service.next_open_id(rows,'a'),'c')
    def test_formresponse_url_alone_does_not_count_as_confirmation(self):
        import sys
        from types import ModuleType,SimpleNamespace
        from unittest.mock import patch
        names=['selenium','selenium.webdriver','selenium.webdriver.common','selenium.webdriver.common.by',
               'selenium.webdriver.support','selenium.webdriver.support.ui']
        modules={name:ModuleType(name) for name in names}
        modules['selenium.webdriver.common.by'].By=SimpleNamespace(CSS_SELECTOR='css')
        class Wait:
            def __init__(self,driver,seconds):self.driver=driver
            def until(self,callback):
                result=callback(self.driver)
                if not result:raise TimeoutError()
                return result
        modules['selenium.webdriver.support.ui'].WebDriverWait=Wait
        driver=Mock();driver.current_url='https://docs.google.com/forms/formResponse'
        driver.find_elements.return_value=[]
        page=sender.SubmissionPage(driver,'robot@example.com')
        with patch.dict(sys.modules,modules):
            with self.assertRaises(TimeoutError):page.wait_for_confirmation()
            receipt=Mock();receipt.text='Your response has been recorded.';receipt.is_displayed.return_value=True
            driver.find_elements.return_value=[receipt]
            self.assertIn('Your response has been recorded.',page.wait_for_confirmation())
            receipt.is_displayed.return_value=False
            with self.assertRaises(TimeoutError):page.wait_for_confirmation()

    def test_uncertain_can_only_be_released_after_explicit_manual_check(self):
        record={**self.record(),'state':'uncertain'}
        with self.assertRaises(ValueError):service.resolve_not_sent(record,'checked','admin',False)
        with self.assertRaises(ValueError):service.resolve_not_sent(record,'','admin',True)
        self.assertEqual(service.resolve_not_sent(record,'Checked response sheet','admin',True)['state'],'prepared')

    def test_bulk_admin_approval_allows_missing_review_fields_without_inventing_agreement(self):
        record=self.record()
        record=service.edit_record({**record,'state':'draft'},
            {**record['data'],'Kategória futárral egyeztetve':'Nem','Reklamáció indoklása':''},'admin')
        changes=service.approve_all_records([record,{**record,'id':'sent','state':'sent'}],'admin')
        self.assertEqual(len(changes),1)
        approved=changes[0][1]
        self.assertTrue(service.admin_approved(approved))
        self.assertEqual(approved['data']['Kategória futárral egyeztetve'],'Nem')
        queued=service.queue_record(approved,'admin')
        page=self.page()
        result=sender.process_record(queued,Mock(),lambda:page)
        self.assertEqual(result['state'],'sent')

    def test_edit_invalidates_bulk_approval_and_requires_review_again(self):
        record={**self.record(),'state':'draft'}
        approved=service.approve_all_records([record],'admin')[0][1]
        changed=service.edit_record(approved,{**approved['data'],'Túra ID':'99999'},'editor')
        self.assertEqual(changed['state'],'draft')
        self.assertFalse(service.admin_approved(changed))
        with self.assertRaises(ValueError):service.queue_record(changed,'editor')


if __name__=='__main__':unittest.main()
