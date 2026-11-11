"""Admin review page: saved data generates fresh, direct Google Form links."""
import hashlib
import json
from datetime import date

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

    notice = st.session_state.pop(KEY+'_notice',None)
    if notice:
        st.success(notice)
    records = st.session_state[KEY]
    if not records:
        st.info('Töltsd be az októberi kategóriajavaslatokat tartalmazó Excelt.')
        return
    cols = st.columns(3)
    for col,state in zip(cols,service.STATES):
        col.metric(service.STATES[state],sum(r['state']==state for r in records))
    st.download_button('Munkapéldány letöltése',json.dumps(records,ensure_ascii=False,indent=2,default=str).encode('utf-8'),
                       file_name='reklamacio_munkapeldany.json',mime='application/json',key='route_form_backup')
    c1,c2,c3 = st.columns([2,1,1])
    search = c1.text_input('Futár, futárazonosító vagy túraszám',key='route_form_search').casefold().strip()
    months = sorted({r['work_date'][:7] for r in records},reverse=True)
    month = c2.selectbox('Hónap',['Összes',*months],key='route_form_month')
    state = c3.selectbox('Státusz',['Összes',*service.STATES.values()],key='route_form_state')
    filtered = [r for r in records if (month=='Összes' or r['work_date'].startswith(month))
                and (state=='Összes' or service.STATES[r['state']]==state)
                and (not search or search in f"{r['courier_name']} {r['courier_id']} {r['route_id']}".casefold())]
    st.dataframe(pd.DataFrame([{'Dátum':r['work_date'],'Futár':r['courier_name'],'Futár ID':r['courier_id'],
                               'Túra':r['route_id'],'Állapot':service.STATES[r['state']]}for r in filtered]),
                 hide_index=True,use_container_width=True)
    if not filtered:
        st.info('Nincs a szűrésnek megfelelő tétel.')
        return
    by_id = {r['id']:r for r in filtered}
    if st.session_state.get('route_form_selected') not in by_id:
        st.session_state['route_form_selected'] = filtered[0]['id']
    selected = st.selectbox('Kezelendő reklamáció',list(by_id),
                           format_func=lambda key:f"{by_id[key]['work_date']} · {by_id[key]['courier_name']} · túra {by_id[key]['route_id']}",key='route_form_selected')
    record = by_id[selected]
    data = record['data']
    if record['state']=='sent':
        st.success(f"Beküldöttként rögzítve: {record.get('submitted_at','')}")
        st.write(record.get('confirmation',''))
        st.info('A tétel zárolt, így nem készül belőle véletlenül újabb beküldés.')
        return
    revision = record['updated_at']
    with st.form('route_form_edit_'+record['id']+'_'+revision):
        a,b,c = st.columns(3)
        day = a.date_input('Érintett nap',value=date.fromisoformat(record['work_date']))
        name = b.text_input('Futár neve',value=record['courier_name'])
        courier = c.text_input('Futár ID',value=record['courier_id'])
        a,b,c = st.columns(3)
        route = a.text_input('Túraszám / Cargo ID',value=record['route_id'])
        warehouse = b.text_input('Raktár',value=str(data.get('Raktár')or''))
        category = c.selectbox('Kategória',list(service.CATEGORY_LABELS),index=int(data['Javasolt kategória száma'])-1,
                               format_func=lambda value:f'{value}. {service.CATEGORY_LABELS[value]}')
        label = service.CATEGORY_LABELS[category]
        reason = st.text_area('Végleges reklamációindoklás',value=str(data.get('Reklamáció indoklása')or''),height=120)
        evidence = st.text_area('Forrásadat / megfontolás',value=str(data.get('Adat / megfontolás')or''),height=100)
        agreed = st.checkbox('Kategória a futárral egyeztetve',value=str(data.get('Kategória futárral egyeztetve')or'').casefold()in{'igen','i','true','1'})
        checked = st.checkbox('Forráseltérés ellenőrizve',value=str(data.get('Forráseltérés ellenőrizve')or'').casefold()in{'igen','i','true','1'})
        if st.form_submit_button('Módosítások mentése',type='primary'):
            changed = {**data,'Dátum':day.isoformat(),'Futár':name,'Futár ID':courier,'Túra ID':route,'Raktár':warehouse,
                       'Javasolt kategória száma':int(category),'Kategóriajavaslat':label,'Reklamáció indoklása':reason,
                       'Adat / megfontolás':evidence,'Kategória futárral egyeztetve':'Igen'if agreed else'Nem',
                       'Forráseltérés ellenőrizve':'Igen'if checked else'Nem'}
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
        st.warning(warning)
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
    with st.expander('Igazolt beküldés rögzítése'):
        confirmation = st.text_input('Visszaigazolás hivatkozása vagy azonosítható megjegyzése',key='route_form_confirmation_'+record['id'])
        acknowledged = st.checkbox('Láttam a Google sikeres beküldési visszaigazolását',key='route_form_ack_'+record['id'])
        if st.button('Beküldöttként rögzítés',disabled=record['state']!='prepared',key='route_form_sent_'+record['id']):
            try:
                save(record,service.confirm_record(record,confirmation,actor,acknowledged))
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
