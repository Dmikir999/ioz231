"""Production adapter: conservative, atomic VK operations and compatible JSON."""
from __future__ import annotations
import copy
from datetime import datetime
from scripts import engine as old
from scripts.vk_language import parse_post
from scripts.vk_reconcile import reconcile

def apply_verified_changes(entries,posts,periods=None):
    schedule=copy.deepcopy(entries);notices=[];applied=[]
    unique={}
    for p in posts:
        if not isinstance(p.get('id'),int):continue
        key=(p.get('owner_id'),p['id'])
        if key not in unique or p.get('edited',0)>=unique[key].get('edited',0):unique[key]=p
    for p in sorted(unique.values(),key=lambda x:(x.get('date',0),x['id'])):
        if not old._target(p.get('text','')):continue
        url=f"https://vk.com/wall{p.get('owner_id','')}_{p['id']}"
        try:
            candidate,report=reconcile(schedule,p,periods)
            if report['status']=='applicable':
                # Preserve all original lesson identities; no generated lessons.
                before=sorted(e['id'] for e in schedule)
                after=sorted(e['id'] for e in candidate)
                if before!=after:raise ValueError('Нарушена идентичность занятий')
                schedule=candidate;applied.append(url);continue
            if report['status']=='irrelevant':continue
            reason=report.get('reason') or '; '.join(x.get('reason','') for x in report['operations'] if x['status']=='review')
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            reason='Не удалось безопасно обработать публикацию: '+type(exc).__name__
        year=datetime.fromtimestamp(p.get('date') or datetime.now(old.TZ).timestamp(),old.TZ).year
        notices.append({'post_id':p['id'],'post_owner':p.get('owner_id',0),'text':old._norm(p.get('text',''))[:600],
                        'timestamp':p.get('date',0),'edited':p.get('edited',0),'url':url,
                        'status':'review','reason':reason or 'Требуется сверка',
                        'lesson_dates':old.parse_dates(p.get('text',''),year)})
    schedule.sort(key=lambda e:(e['date'],e['time'],e['subject']))
    return schedule,notices,applied
