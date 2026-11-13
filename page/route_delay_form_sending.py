"""Admin review page: saved data generates fresh, direct Google Form links."""
import hashlib
import json
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st
from resources import route_delay_form_drafts as service

KEY = 'route_delay_form_records'


def render_route_delay_form_sending(get_db, user):
    st.title('Reklamációk elküldése')
    st.caption('Excel betöltése → adatok ellenőrzése és mentése → Google-űrlap előkitöltése → kézi beküldés és visszaigazolás.')
    actor = str(user.get('username') or '')
    if st.button('Mentett reklamációk újratöltése', key='reload_route_form_drafts'):
        try:
            loaded = service.load_records(get_db())
            st.session_state[KEY] = loaded
            st.session_state[KEY+'_persistent'] = True
        except Exception:
            st.error('A mentett lista most nem tölthető be. A jelenlegi munkapéldány megmaradt.')
    if KEY not in st.session_state:
        try:
            st.session_state[KEY] = service.load_records(get_db())
            st.session_state[KEY+'_persistent'] = True
        except Exception:
            st.session_state[KEY] = []
            st.session_state[KEY+'_persistent'] = False
    persistent = st.session_state[KEY+'_persistent']
    if persistent and st.session_state.get(KEY+'_batch_waiting'):
        try:
            st.session_state[KEY]=service.load_records(get_db())
            progress=st.session_state[KEY]
            active=sum(r['state']in{'queued','processing'}for r in progress)
            uncertain=sum(r['state']=='uncertain'for r in progress)
            st.info(f'Beküldési sor: {active} várakozó vagy folyamatban; {uncertain} ellenőrizendő eredmény.')
            if active or uncertain:
                from streamlit_autorefresh import st_autorefresh
                st_autorefresh(interval=3000,key='route_batch_submission_poll')
            else:
                st.session_state.pop(KEY+'_batch_waiting',None)
                st.session_state[KEY+'_notice']='A beküldési sor feldolgozása befejeződött. Az eredmények a státuszoszlopban láthatók.'
        except Exception:
            st.warning('A beküldési sor állapota most nem olvasható. Új beküldés helyett töltsd újra a mentett listát.')
    if persistent and st.session_state.get(KEY+'_waiting'):
        try:
            refreshed=service.load_records(get_db())
            st.session_state[KEY]=refreshed
            waiting=st.session_state[KEY+'_waiting']
            result=next((r for r in refreshed if r['id']==waiting),None)
            if result and result['state']=='sent':
                st.session_state.pop(KEY+'_waiting',None)
                candidates=st.session_state.pop(KEY+'_next_candidates',[])
                ordered=[next(r for r in refreshed if r['id']==key) for key in candidates
                         if any(r['id']==key for r in refreshed)]
                next_id=service.next_open_id(ordered,waiting)
                if next_id:
                    st.session_state['route_form_selected']=next_id
                st.session_state[KEY+'_notice']='A Google visszaigazolta a beküldést. A következő nyitott reklamáció kiválasztva.' if next_id else 'A Google visszaigazolta a beküldést. Nincs több nyitott tétel a listában.'
            elif result and result['state'] not in {'queued','processing'}:
                st.session_state.pop(KEY+'_waiting',None)
                st.session_state.pop(KEY+'_next_candidates',None)
        except Exception:
            st.warning('A beküldés állapota most nem olvasható. Ne indíts új beküldést; töltsd újra a mentett listát.')
        if st.session_state.get(KEY+'_waiting'):
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=3000,key='route_submission_poll')
    if not persistent:
        st.info('A tartós mentés most nem érhető el. A feltöltött tételek ebben a munkamenetben szerkeszthetők; kilépés előtt töltsd le a munkapéldányt.')

    def save(previous, replacement):
        current = st.session_state[KEY]
        proposed = [replacement if r['id']==previous['id'] else r for r in current]
        service.assert_unique(proposed)
        if persistent:
            service.store_edit(get_db(), previous, replacement)
        st.session_state[KEY] = proposed

    with st.expander('Excel betöltése', expanded=not st.session_state[KEY]):
        uploaded = st.file_uploader('Excel vagy korábban letöltött JSON-munkapéldány', type=['xlsx','json'], key='route_form_excel_upload')
        if uploaded:
            content = uploaded.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            if st.session_state.get(KEY+'_upload_digest')!=digest:
                try:
                    incoming = (service.read_backup(content,actor) if uploaded.name.lower().endswith('.json')
                                else service.read_excel(content, uploaded.name, actor))
                    st.session_state[KEY+'_preview'] = incoming
                    st.session_state[KEY+'_upload_digest'] = digest
                except Exception as exc:
                    st.session_state.pop(KEY+'_preview',None)
                    st.error(f'Az Excel nem olvasható: {exc}')
            incoming = st.session_state.get(KEY+'_preview',[])
            if incoming:
                st.write(f'{len(incoming)} túra ellenőrizve. A betöltés nem küld be reklamációt.')
                overwrite = st.checkbox('Meglévő, még be nem küldött tervezetek felülírása az Excel adataival', key='route_form_overwrite')
                if st.button('Excel tételeinek betöltése', type='primary', key='route_form_import'):
                    try:
                        current = st.session_state[KEY]
                        combined, counts = service.merge_import(current,incoming,overwrite)
                        service.assert_unique(combined)
                        if persistent:
                            old = {r['id']:r for r in current}
                            service.store_records(get_db(),[r for r in combined if r['id'] not in old])
                            for row in combined:
                                if row['id'] in old and row['content_hash']!=old[row['id']]['content_hash']:
                                    service.store_edit(get_db(),old[row['id']],row)
                            combined = service.load_records(get_db())
                        st.session_state[KEY] = combined
                        st.session_state[KEY+'_notice'] = f"Betöltve: {counts['added']} új, {counts['updated']} módosított; {counts['skipped']} változatlan vagy védett tétel."
                        st.rerun()
                    except Exception as exc:
                        st.error(f'A betöltés nem sikerült: {exc}. Újrapróbálás előtt töltsd újra a mentett listát.')

    with st.expander('Októberi Elszámolás-sorlista beillesztése', expanded=False):
        st.caption('Illeszd be a 9 oszlopos, tabulátoros listát. Minden sor külön, ellenőrizhető Google-űrlaptervezet lesz. A Route ID hiánya Elszámolásnál megengedett.')
        invoice_paste = st.text_area(
            'Dátum · futár · ID · Route ID · raktár · tervezett kezdés · Hub · Giriton · sorbaállás',
            height=220, key='invoice_form_paste',
        )
        invoice_message = st.text_area(
            'A Google-űrlapra kerülő közös Elszámolás-szöveg',
            height=180, key='invoice_form_message',
            value=(
                'Az Október 7.-i változtatás miszerint csak és kizárólag a flotta által allokált autókat lehet használni megborította az októberi beosztást, hiszen nem tudtuk pontosan addig a napig, hogy mennyi autót fogunk kezelésbe kapni, folyamatos éreklődésünkre "még folyamatban vannak az igényfelmérések"-választ kaptuk. Mivel erről a helyzetről a futár nem tehetett azt az infomrációt kaptuk, hogy a hónapban az autóra/telefonra való várakozás esetén felmerült nem teljesítés esetén a no-show-tól eltekintenek.'
            ),
        )
        if st.button('Elszámolás-tervezetek előkészítése és mentése', type='primary', key='invoice_form_import'):
            try:
                incoming = service.read_invoice_paste(invoice_paste, invoice_message, actor=actor)
                current = st.session_state[KEY]
                combined, counts = service.merge_import(current, incoming, overwrite=False)
                service.assert_unique(combined)
                if persistent:
                    old = {row['id']: row for row in current}
                    service.store_records(get_db(), [row for row in combined if row['id'] not in old])
                    combined = service.load_records(get_db())
                st.session_state[KEY] = combined
                st.session_state[KEY+'_notice'] = (
                    f"Elszámolás-tervezetek mentve: {counts['added']} új, "
                    f"{counts['skipped']} már létező vagy védett tétel. Beküldés még nem történt."
                )
                st.rerun()
            except Exception as exc:
                st.error(f'A sorlista feldolgozása nem sikerült: {exc}')

    with st.expander('Első műszak késések Excel automatikus Elszámolás-import', expanded=False):
        st.caption('Az „Első műszak késések” lapból csak a Hub `OK` sorok kerülnek be. A Giriton- és sorbaállási adatok az ellenőrizhető belső forrásadatok között maradnak.')
        invoice_excel = st.file_uploader(
            'oktober_elso_muszak_hub_giriton_2026.xlsx', type=['xlsx'], key='invoice_form_excel_upload'
        )
        if invoice_excel and st.button('OK sorok Elszámolás-tervezetként mentése', type='primary', key='invoice_excel_import'):
            try:
                incoming = service.read_invoice_excel(
                    invoice_excel.getvalue(), invoice_excel.name, actor=actor,
                    message=service.INVOICE_FLEET_MESSAGE,
                )
                current = st.session_state[KEY]
                combined, counts = service.merge_import(current, incoming, overwrite=False)
                service.assert_unique(combined)
                if persistent:
                    old = {row['id']: row for row in current}
                    service.store_records(get_db(), [row for row in combined if row['id'] not in old])
                    combined = service.load_records(get_db())
                st.session_state[KEY] = combined
                st.session_state[KEY+'_notice'] = (
                    f"{len(incoming)} OK sor feldolgozva: {counts['added']} új tervezet, "
                    f"{counts['skipped']} már létező vagy védett tétel. Beküldés még nem történt."
                )
                st.rerun()
            except Exception as exc:
                st.error(f'Az Excel automatikus feldolgozása nem sikerült: {exc}')

    notice = st.session_state.pop(KEY+'_notice',None)
    if notice:
        st.success(notice)
    records = st.session_state[KEY]
    if not records:
        st.info('Töltsd be az októberi kategóriajavaslatokat tartalmazó Excelt, vagy illeszd be az Elszámolás-sorlistát.')
        return
    cols = st.columns(3)
    for col,state in zip(cols,['draft','prepared','sent']):
        col.metric(service.STATES[state],sum(r['state']==state for r in records))
    ready=sum(r['state']=='prepared'for r in records)
    blocked=any(r['state']in{'queued','processing','uncertain'}for r in records)
    st.subheader('Összes reklamáció beküldése')
    st.caption('A tömeges jóváhagyás a jelenlegi adatokat és a rövid levélszöveget fogadja el. '
               'Nem jelöl futárral történt egyeztetést; a jóváhagyó neve és az időpont külön mentődik. '
               'Későbbi tartalmi módosítás új jóváhagyást igényel.')
    if st.button('Összes jelenlegi tervezet és szöveg jóváhagyása',disabled=blocked,key='route_approve_all'):
        try:
            changes=service.approve_all_records(records,actor)
            for previous,replacement in changes:
                save(previous,replacement)
            st.session_state[KEY+'_notice']=f'{len(changes)} reklamáció és levélszöveg adminisztrátori jóváhagyása mentve.'
            st.rerun()
        except Exception as exc:
            st.error(f'A jóváhagyás megszakadt: {exc}. A már mentett állapotok megmaradtak; töltsd újra a listát.')
    st.write(f'{ready} ellenőrzött reklamáció küldhető be. '
             f"{sum(r['state']=='draft'for r in records)} tervezet még ellenőrzésre vár. "
             f"{sum(r['state']=='sent'for r in records)} tétel már beküldve.")
    st.caption('A gomb a teljes betöltött lista ellenőrzött tételeit küldi be, a keresési szűrőtől függetlenül. '
               'A Google-robot egyenként kitölti az űrlapokat és megnyomja a Küldést. Az első hibánál megáll.')
    if st.button(f'Összes ellenőrzött reklamáció beküldése ({ready})',type='primary',
                 use_container_width=True,disabled=not persistent or not ready or blocked,key='route_submit_all'):
        try:
            count=service.queue_batch(get_db(),records,actor)
            st.session_state[KEY]=service.load_records(get_db())
            st.session_state[KEY+'_batch_waiting']=True
            st.session_state[KEY+'_notice']=f'{count} reklamáció beküldésre sorba állítva.'
            st.rerun()
        except Exception as exc:
            st.error(f'A beküldési sor nem indult el: {exc}')
    st.download_button('Munkapéldány letöltése',json.dumps(records,ensure_ascii=False,indent=2,default=str).encode('utf-8'),
                       file_name='reklamacio_munkapeldany.json',mime='application/json',key='route_form_backup')
    c1,c2,c3 = st.columns([2,1,1])
    search = c1.text_input('Futár, futárazonosító vagy túraszám',key='route_form_search').casefold().strip()
    months = sorted({r['work_date'][:7] for r in records},reverse=True)
    month = c2.selectbox('Hónap',['Összes',*months],key='route_form_month')
    state = c3.selectbox('Státusz',['Összes',*service.STATES.values()],key='route_form_state')
    filtered = [r for r in records if (month=='Összes' or r['work_date'].startswith(month))
                and (state=='Összes' or service.STATES[r['state']]==state)
                and (not search or search in f"{r['courier_name']} {r['courier_id']} {service.display_route_id(r)}".casefold())]
    st.dataframe(pd.DataFrame([{'Dátum':r['work_date'],'Futár':r['courier_name'],'Futár ID':r['courier_id'],
                               'Túra':service.display_route_id(r),'Állapot':service.STATES[r['state']]}for r in filtered]),
                 hide_index=True,use_container_width=True)
    if not filtered:
        st.info('Nincs a szűrésnek megfelelő tétel.')
        return
    by_id = {r['id']:r for r in filtered}
    if st.session_state.get('route_form_selected') not in by_id:
        st.session_state['route_form_selected'] = filtered[0]['id']
    selected = st.selectbox('Kezelendő reklamáció',list(by_id),
                           format_func=lambda key:f"{by_id[key]['work_date']} · {by_id[key]['courier_name']} · túra {service.display_route_id(by_id[key]) or 'nincs Route ID'}",key='route_form_selected')
    record = by_id[selected]
    data = record['data']
    if record['state']=='sent':
        st.success(f"Beküldöttként rögzítve: {record.get('submitted_at','')}")
        st.write(record.get('confirmation',''))
        st.info('A tétel zárolt, így nem készül belőle véletlenül újabb beküldés.')
        return
    if record['state'] in {'queued','processing'}:
        st.info('A reklamáció beküldésre vár.' if record['state']=='queued' else 'A robot kitölti és beküldi az űrlapot. A Google visszaigazolására várunk.')
        st.caption('A külön Google-robotnak futnia kell. A következő reklamáció nem kerül automatikusan beküldésre.')
        if record['state']=='processing' and (datetime.now(timezone.utc)-datetime.fromisoformat(record['updated_at'].replace('Z','+00:00'))).total_seconds()>300:
            if st.button('Elakadt beküldés megjelölése ellenőrizendőként',key='route_stuck_'+record['id']):
                try:
                    save(record,{**record,'state':'uncertain','confirmation':'A feldolgozás megszakadhatott; kézi ellenőrzés szükséges.',
                                 'updated_at':datetime.now(timezone.utc).isoformat(),'updated_by':actor})
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        if not st.session_state.get(KEY+'_waiting'):
            st.session_state[KEY+'_waiting']=record['id']
            st.session_state[KEY+'_next_candidates']=[r['id'] for r in filtered]
            st.rerun()
        return
    if record['state']=='uncertain':
        st.error('A beküldés eredménye bizonytalan. Ne küldd újra: ellenőrizd a Google-űrlapot vagy a visszaigazoló levelet.')
        st.write(record.get('confirmation',''))
        with st.form('route_uncertain_confirmation_'+record['id']):
            proof=st.text_input('Sikeres beküldés visszaigazolása')
            ack=st.checkbox('Ellenőriztem: a Google rögzítette ezt a reklamációt')
            if st.form_submit_button('Igazolt beküldés rögzítése'):
                try:
                    save(record,service.confirm_record(record,proof,actor,ack))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with st.expander('Ellenőriztem: nem történt beküldés'):
            note=st.text_input('Hol ellenőrizted a beküldés hiányát?',key='route_not_sent_note_'+record['id'])
            verified=st.checkbox('A Google-válaszok vagy visszaigazolások alapján nem került beküldésre',key='route_not_sent_ack_'+record['id'])
            if st.button('Feloldás új beküldéshez',key='route_not_sent_'+record['id']):
                try:
                    save(record,service.resolve_not_sent(record,note,actor,verified))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        return
    revision = record['updated_at']
    with st.form('route_form_edit_'+record['id']+'_'+revision):
        a,b,c = st.columns(3)
        day = a.date_input('Érintett nap',value=date.fromisoformat(record['work_date']))
        name = b.text_input('Futár neve',value=record['courier_name'])
        courier = c.text_input('Futár ID',value=record['courier_id'])
        a,b,c = st.columns(3)
        route = a.text_input('Túraszám / Cargo ID',value=service.display_route_id(record))
        warehouse = b.text_input('Raktár',value=str(data.get('Raktár')or''))
        is_invoice = str(data.get('Űrlap kategória') or '') == 'Elszámolás'
        if is_invoice:
            c.text_input('Google-űrlap kategória', value='Elszámolás / Invoice', disabled=True)
            reason = st.text_area('Google-űrlapra kerülő szöveg',value=str(data.get('Reklamáció indoklása')or''),height=180)
            evidence = st.text_area('Mentett forrásadat / megfontolás',value=str(data.get('Adat / megfontolás')or''),height=100)
        else:
            category = c.selectbox('Kategória',list(service.CATEGORY_LABELS),index=int(data['Javasolt kategória száma'])-1,
                                   format_func=lambda value:f'{value}. {service.CATEGORY_LABELS[value]}')
            label = service.CATEGORY_LABELS[category]
            reason = st.text_area('Végleges reklamációindoklás',value=str(data.get('Reklamáció indoklása')or''),height=120)
            evidence = st.text_area('Forrásadat / megfontolás',value=str(data.get('Adat / megfontolás')or''),height=100)
            agreed = st.checkbox('Kategória a futárral egyeztetve',value=str(data.get('Kategória futárral egyeztetve')or'').casefold()in{'igen','i','true','1'})
            checked = st.checkbox('Forráseltérés ellenőrizve',value=str(data.get('Forráseltérés ellenőrizve')or'').casefold()in{'igen','i','true','1'})
        if st.form_submit_button('Módosítások mentése',type='primary'):
            changed = {**data,'Dátum':day.isoformat(),'Futár':name,'Futár ID':courier,'Túra ID':route,'Raktár':warehouse,
                       'Reklamáció indoklása':reason,'Adat / megfontolás':evidence}
            if not is_invoice:
                changed.update({'Javasolt kategória száma':int(category),'Kategóriajavaslat':label,
                                'Kategória futárral egyeztetve':'Igen'if agreed else'Nem',
                                'Forráseltérés ellenőrizve':'Igen'if checked else'Nem'})
                # Drop editable-workbook aliases so older values cannot overwrite edits.
                changed.pop('Kategória száma',None)
                changed.pop('Végleges indoklás',None)
            try:
                save(record,service.edit_record(record,changed,actor))
                st.session_state[KEY+'_notice']='A tétel mentve. Az űrlaplink már az új adatokat használja.'
                st.rerun()
            except Exception as exc:
                st.error(f'A mentés nem sikerült: {exc}')

    draft = service.preparation.prepare_row(record['data'],record['source_row'])
    for warning in draft['warnings']:
        if not service.admin_approved(record):
            st.warning(warning)
    if service.admin_approved(record):
        approval=record['data']['_admin_approval']
        st.info(f"Adminisztrátori jóváhagyás: {approval['actor']} · {approval['approved_at']}")
    st.text_area('Google-űrlapra kerülő szöveg',value=draft['payload']['description'],height=260,disabled=True,
                 key='route_form_preview_'+record['id']+'_'+revision)
    st.link_button('Google-űrlap előkitöltése',draft['prefill_url'],use_container_width=True)
    st.caption('A link a mentett adatokat használja. A Google-űrlapon ellenőrizd a fiókot, majd kattints a Következő gombra. A Küldés gombot te nyomod meg.')
    if st.button('Adatok ellenőrizve',disabled=bool(draft['warnings'])or record['state']=='prepared',key='route_form_checked_'+record['id']):
        try:
            save(record,service.prepare_record(record,actor))
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    st.caption('A Beküldés gomb a mentett adatokat átadja a Google-robotnak. A robot a Küldés gombot is megnyomja; csak sikeres visszaigazolás után lépünk tovább.')
    if not persistent:
        st.info('Az egygombos beküldéshez tartós adatbázis-mentés szükséges.')
    if st.button('Beküldés és következő futár',type='primary',use_container_width=True,
                 disabled=not persistent or record['state']!='prepared' or (bool(draft['warnings']) and not service.admin_approved(record)),
                 key='route_submit_next_'+record['id']):
        try:
            save(record,service.queue_record(record,actor))
            st.session_state[KEY+'_waiting']=record['id']
            st.session_state[KEY+'_next_candidates']=[r['id']for r in filtered]
            st.rerun()
        except Exception as exc:
            st.error(f'A beküldés nem indult el: {exc}')
    with st.expander('Igazolt beküldés rögzítése'):
        confirmation = st.text_input('Visszaigazolás hivatkozása vagy azonosítható megjegyzése',key='route_form_confirmation_'+record['id'])
        acknowledged = st.checkbox('Láttam a Google sikeres beküldési visszaigazolását',key='route_form_ack_'+record['id'])
        if st.button('Beküldöttként rögzítés',disabled=record['state']!='prepared',key='route_form_sent_'+record['id']):
            try:
                save(record,service.confirm_record(record,confirmation,actor,acknowledged))
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
