"""Read-only monthly complaint index, including couriers without complaints."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

TOPICS = {'noShow':'NO-SHOW reklamációk', 'shiftProblem':'Műszak problémák',
          'lateShift':'Műszakkésés', 'customerDelay':'Ügyfélkésés reklamációk', 'other':'Egyéb reklamációk'}


def category(topic):
    if topic == 'noShow': return 'noShow'
    if topic in {'lateShift','shift_late','coordinator_shift_late'}: return 'lateShift'
    if topic in {'uncleanedTimeWindowLate','cleanedTimeWindowLate','delay'}: return 'customerDelay'
    if topic in {'shift','Műszak','bag_missing'}: return 'shiftProblem'
    return 'other'


def monthly_workspace(month, read):
    start=month.replace(day=1)
    stop=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    warnings=[]
    def rows(table, params):
        result=[]
        try:
            for offset in range(0,50000,500):
                page=read(table,{**params,'limit':'500','offset':str(offset)}) or []
                result.extend(page)
                if len(page)<500:return result
            warnings.append(table+': a lista elérte az 50 000 soros korlátot.')
        except Exception:
            warnings.append(table+': az adatforrás nem olvasható; az adatai hiányozhatnak.')
        return result
    master=rows('courier_master',{'select':'courier_id,courier_name,warehouse_name','order':'courier_id.asc'})
    couriers={str(r['courier_id']):{'courierId':str(r['courier_id']),'courierName':r.get('courier_name') or str(r['courier_id']),
              'warehouse':r.get('warehouse_name') or '', 'days':{}} for r in master}
    def add(cid,name,day,kind,item):
        if not day or not start.isoformat()<=day<stop.isoformat():return
        cid=str(cid or '')
        if not cid:return
        courier=couriers.setdefault(cid,{'courierId':cid,'courierName':name or cid,'warehouse':'','days':{}})
        group=courier['days'].setdefault(day,{'date':day,'items':[]})
        group['items'].append({**item,'category':kind})
    complaints=rows('pwa_quality_complaints',{'select':'id,courier_id,courier_name,topic,status,message,affected_items',
                    'work_month':'eq.'+start.isoformat(),'order':'id.asc'})
    for r in complaints:
        for day in {str(i.get('date')or'')[:10] for i in r.get('affected_items')or[]}:
            add(r['courier_id'],r.get('courier_name'),day,category(r.get('topic')),
                {'id':str(r['id']),'source':'complaint','status':r.get('status'),'message':r.get('message')or''})
    routes=rows('courier_hub_route_statistics',{'select':'courier_id,route_id,work_date','work_date':'gte.'+start.isoformat(),
                 'and':f'(work_date.lt.{stop.isoformat()})','order':'route_id.asc,courier_id.asc'})
    route_days={(str(r['courier_id']),str(r['route_id'])):r['work_date'] for r in routes}
    alerts=rows('courier_route_alerts',{'select':'id,courier_id,courier_name,route_id,alert_type,message,status,created_at','order':'id.asc'})
    for r in alerts:
        day=route_days.get((str(r['courier_id']),str(r.get('route_id'))))
        if not day:
            # An undated signal cannot establish the day worked.
            continue
        add(r['courier_id'],r.get('courier_name'),day,category(r.get('alert_type')),
            {'id':str(r['id']),'source':'route','routeId':str(r.get('route_id')or''),'status':r.get('status'),'message':r.get('message')or''})
    shifts=rows('courier_shift_checkins',{'select':'id,courier_id,courier_name,work_date,event_type,shift_name',
                 'work_date':'gte.'+start.isoformat(),'and':f'(work_date.lt.{stop.isoformat()})','order':'id.asc'})
    for r in shifts:
        if r.get('event_type') not in {'shift_late','coordinator_shift_late'}:continue
        add(r['courier_id'],r.get('courier_name'),r['work_date'],category(r['event_type']),
            {'id':str(r['id']),'source':'shift','status':'signal','message':r.get('shift_name')or''})
    drafts=rows('settlement.route_delay_form_draft',{'select':'id,courier_id,work_date,route_id,state,data',
                  'work_date':'gte.'+start.isoformat(),'and':f'(work_date.lt.{stop.isoformat()})','order':'id.asc'})
    for r in drafts:
        add(r['courier_id'],(r.get('data')or{}).get('Futár'),r['work_date'],'customerDelay',
            {'id':str(r['id']),'source':'google','routeId':str(r.get('route_id')or''),'status':r['state'],
             'message':(r.get('data')or{}).get('Reklamáció indoklása')or (r.get('data')or{}).get('Kategóriajavaslat')or''})
    result=[]
    for r in couriers.values():
        r['days']=sorted(r['days'].values(),key=lambda x:x['date'],reverse=True)
        result.append(r)
    return {'month':start.strftime('%Y-%m'),'couriers':sorted(result,key=lambda x:x['courierName'].casefold()),'warnings':warnings,'categories':TOPICS}
