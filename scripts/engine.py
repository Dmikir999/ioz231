"""Rebuilds the published ИОЗ-231 schedule with conservative VK post updates."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import re
from datetime import datetime, date, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo

from scripts.xlsx_reader import GROUP, parse_xlsx

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'data'
DOCS=ROOT/'docs'
TZ=ZoneInfo('Europe/Moscow')
MAIL='https://cloud.mail.ru/public/TKBt/bHWaZqMQA'
VK='https://vk.com/dekanat_ign'
GROUP_RE=re.compile(r'(?<![А-ЯA-Z0-9])И\s*[ОO0]\s*[З3]\s*[-–— ]?\s*231(?!\d)',re.I)
ANY_GROUP_RE=re.compile(r'(?<![А-ЯA-Z0-9])И\s*[ОO0]\s*[З3]\s*[-–— ]?\s*(\d{3})(?!\d)',re.I)
DATE_RE=re.compile(r'(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)')
TIME_RE=re.compile(r'(?<!\d)([012]?\d)[:.]([0-5]\d)(?!\d)')
MONTHS={'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}
MONTH_RE=re.compile(r'(?<!\d)(\d{1,2})\s+('+'|'.join(MONTHS)+r')(?:\s+(20\d{2}))?',re.I)
LOG=logging.getLogger('ioz231')
logging.basicConfig(level=logging.INFO,format='%(levelname)s: %(message)s')


def _json_get(url,params=None):
    if params:url+='?'+urlencode(params)
    req=Request(url,headers={'User-Agent':'IOZ231Schedule/2.0 (university timetable)','Accept':'application/json'})
    with urlopen(req,timeout=28) as resp:
        return json.load(resp)


def _download(url):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 IOZ231Schedule/2.0'})
    with urlopen(req,timeout=40) as resp:
        blob=resp.read(5_000_000)
    if blob[:2]!=b'PK':raise ValueError('Ссылка вернула HTML или другой формат вместо XLSX')
    return blob


def _mail_download_hosts(dispatcher):
    """Extract ephemeral download endpoints from Mail's dispatcher response."""
    raw=(dispatcher.get('body') or {}).get('weblink_get') or []
    if isinstance(raw,(str,dict)):
        raw=[raw]
    hosts=[]
    for item in raw:
        host=item.get('url','') if isinstance(item,dict) else item
        if isinstance(host,str) and host.startswith('https://'):
            hosts.append(host.rstrip('/'))
    return hosts


def fetch_mail_xlsx(source):
    # Manual override is useful for diagnostics, but Cloud Mail links expire:
    # the normal path must resolve a new URL on *every* check.
    direct=os.getenv('XLSX_DIRECT_URL','').strip()
    if direct and source == MAIL:
        try:
            return _download(direct)
        except Exception as exc:
            LOG.warning('XLSX_DIRECT_URL is unavailable; trying public link: %s',exc)
    # Mail returns weblink_get as a LIST OF DICTS containing "url", not
    # merely strings. Previously every valid dispatcher host was discarded.
    result=_json_get('https://cloud.mail.ru/api/v2/dispatcher',{'api':'2','build':'cloudweb-1'})
    hosts=_mail_download_hosts(result)
    if not hosts:
        raise RuntimeError('Mail Cloud dispatcher returned no HTTPS weblink_get endpoint')
    for host in hosts:
        try:
            return _download(host+'/'+source.split('/public/', 1)[1])
        except Exception as exc:
            LOG.warning('Mail download endpoint failed: %s',exc)
    raise RuntimeError('Не удалось скачать XLSX ни с одного адреса Mail Cloud')


def _norm(v):return ' '.join(str(v or '').split())
def _target(v):return bool(GROUP_RE.search(_norm(v)))


def parse_dates(text,ref_year=2026):
    result=set()
    for m in DATE_RE.finditer(text):
        day,month,year=m.groups();yy=int(year) if year else ref_year
        if yy<100:yy+=2000
        try:result.add(date(yy,int(month),int(day)).isoformat())
        except ValueError:pass
    for m in MONTH_RE.finditer(text):
        d,month,y=m.groups()
        try:result.add(date(int(y or ref_year),MONTHS[month.lower()],int(d)).isoformat())
        except ValueError:pass
    return sorted(result)


def parse_time(s):
    m=TIME_RE.search(s)
    if not m:return ''
    h,minute=map(int,m.groups())
    return f'{h:02d}:{minute:02d}' if h<24 else ''


def detect_change(post):
    txt=_norm(post.get('text',''))
    if not _target(txt):return None
    id=post.get('id')
    if not isinstance(id,int):return None
    base={'post_id':id,'post_owner':post.get('owner_id',0),'text':txt[:600],
          'timestamp':post.get('date',0),'edited':post.get('edited',0),
          'url':f'https://vk.com/wall{post.get("owner_id", "")}_{id}'}
    def review(reason):return {**base,'status':'review','reason':reason}
    groups=set(ANY_GROUP_RE.findall(txt))
    if groups-{'231'}:return review('В публикации несколько групп')
    post_year=datetime.fromtimestamp(post.get('date') or datetime.now(TZ).timestamp(),TZ).year
    dates=parse_dates(txt,post_year)
    if len(dates)!=1:return review('Нет одной однозначной даты')
    if post.get('attachments'):
        # Images and PDFs require OCR; cannot reliably infer the change from an attachment.
        return review('Публикация содержит вложение: требуется сверка с изображением/файлом')
    if re.search(r'замен[аеы]|вместо|изменени[ея]',txt,re.I) and not re.search(r'ауд|каб|время|перенос|отмен',txt,re.I):
        return review('Замена предмета или преподавателя требует проверки')
    cancel=bool(re.search(r'отмен(?:а|яется|ены|ена|ён)|не\s+состоится',txt,re.I))
    movement=re.search(r'\bс\s*(\d{1,2}[:.]\d{2})\s+на\s*(\d{1,2}[:.]\d{2})',txt,re.I)
    new_room=re.search(r'(?:в\s+(?:ауд(?:итории|\.)?|кабинете)\s*|ауд(?:итория|\.)?\s*[№#:]?\s*)(\d{3,5})',txt,re.I)
    is_room_change=bool(re.search(r'аудитор\w*\s*(?:измен|замен|перенос)|измен\w*\s+аудитор|вместо\s+аудитор|будет\s+в\s+ауд',txt,re.I))
    # Prefer old start time with explicit "с ... на ...". Otherwise require exactly one time.
    times=[parse_time(x.group()) for x in TIME_RE.finditer(DATE_RE.sub(' ',txt))]
    if movement:
        old=parse_time(movement.group(1));new=parse_time(movement.group(2))
    elif len(set(times))==1:
        old=times[0];new=''
    else:
        return review('Не указано единственное время занятия')
    if not old:return review('Не удалось определить время занятия')
    if not cancel and not movement and not (new_room and is_room_change):
        return review('Тип изменения неоднозначен')
    if movement and not new:return review('Новое время не распознано')
    if cancel and movement:return review('Одновременно отмена и перенос — нужна проверка')
    return {**base,'status':'candidate','date':dates[0], 'time':old,
            'new_time':new,'room':new_room.group(1) if (new_room and is_room_change) else '',
            'cancelled':cancel}


def fetch_vk_posts():
    token=os.getenv('VK_TOKEN','').strip()
    if not token:raise RuntimeError('Не задан VK_TOKEN: посты ВКонтакте автоматически не проверяются')
    js=_json_get('https://api.vk.com/method/wall.get',
                {'domain':'dekanat_ign','count':100,'access_token':token,'v':'5.199'})
    if 'error' in js:raise RuntimeError('VK API: '+str(js['error'].get('error_msg','неизвестная ошибка')))
    return js.get('response',{}).get('items',[])


def apply_changes(entries,posts):
    schedule=[dict(e) for e in entries]
    notices=[];applied=[]
    ordered=sorted(posts,key=lambda post:(post.get('date',0),post.get('edited',0),post.get('id',0)))
    for post in ordered:
        change=detect_change(post)
        if not change:continue
        if change['status']!='candidate':notices.append(change);continue
        # Match by the *original* timetable time, so edited VK messages don't cascade.
        matches=[i for i,e in enumerate(entries) if e['date']==change['date'] and e['time']==change['time']]
        if len(matches)!=1:
            notices.append({**change,'status':'review','reason':f'Не найдено ровно одной пары: найдено {len(matches)}'})
            continue
        idx=matches[0]
        if change['cancelled']:
            schedule[idx]['cancelled']=True
        else:
            if change['new_time']:
                schedule[idx]['previous_time']=entries[idx]['time']
                schedule[idx]['time']=change['new_time']
                # Do not guess new end time; keep the original duration as text, if necessary.
                schedule[idx]['end']=''
            if change['room']:schedule[idx]['room']=change['room']
            schedule[idx].pop('cancelled',None)
        schedule[idx]['changed']=True
        schedule[idx]['change_url']=change['url']
        applied.append(change['url'])
    return schedule,notices,applied


def read_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def run():
    DATA.mkdir(parents=True,exist_ok=True);DOCS.mkdir(parents=True,exist_ok=True)
    now=datetime.now(TZ)
    base=read_json(DATA/'base.json',{})
    config = json.loads((ROOT/'semester.json').read_text(encoding='utf-8'))
    source = config['source'].strip().rstrip('/')
    if not re.fullmatch(r'https://cloud\.mail\.ru/public/[\w-]+/[\w-]+', source):
        raise ValueError('Укажите публичную ссылку Облака Mail на файл XLSX')
    periods = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in config['periods']]
    if not periods or any(a > b for a, b in periods) or any(
        previous[1] >= current[0] for previous, current in zip(periods, periods[1:])
    ) or (periods[-1][1] - periods[0][0]).days >= 365:
        raise ValueError('Проверьте порядок и границы учебных периодов')
    switching = config != base.get('semester')
    entries=base.get('entries',[])
    if base.get('group')!=GROUP:entries=[]
    warnings=[];errors=[];source_live=False
    try:
        blob=fetch_mail_xlsx(source)
        live,parse_warnings=parse_xlsx(blob, config['sheet'], periods)
        if not live:raise ValueError('Новый файл не содержит занятий')
        if switching and parse_warnings:
            raise ValueError('Проверьте новую таблицу: ' + '; '.join(parse_warnings[:3]))
        entries=live;warnings.extend(parse_warnings);source_live=True
        checksum=hashlib.sha256(blob).hexdigest()
        # Save a GROUP-ONLY cached version, never the entire XLSX of other students.
        new_base={'group':GROUP,'source':source,'source_sheet':config['sheet'],'semester':config,'sha256':checksum,
                  'imported_at':now.isoformat(),'entries':entries,'warnings':warnings}
        if switching or base.get('sha256')!=checksum:
            (DATA/'base.json').write_text(json.dumps(new_base,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            LOG.info('Updated source XLSX from Cloud Mail: %d lessons',len(entries))
    except Exception as exc:
        if switching:
            raise RuntimeError('Семестр не подключён. Сохранена предыдущая публикация: ' + str(exc)) from exc
        errors.append('Источник Excel: '+str(exc))
        if not entries:LOG.error('No verified baseline and Mail unavailable: %s',exc)
        else:LOG.warning('Using saved verified baseline: %s',exc)
        warnings.extend(base.get('warnings',[]))
    posts_history=read_json(DATA/'posts.json',{'group':GROUP,'items':[]})
    known={str(x['id']):x for x in posts_history.get('items',[]) if isinstance(x,dict) and 'id' in x}
    vk_ok=False
    try:
        new_posts=fetch_vk_posts();vk_ok=True
        # Retain posts relating to ИОЗ-231 even if they fall out of the latest VK feed.
        for post in new_posts:
            if _target(post.get('text','')):
                known[str(post['id'])]={
                    'id':post['id'], 'owner_id':post.get('owner_id',0),
                    'date':post.get('date',0),'edited':post.get('edited',0),
                    'text':post.get('text',''),
                    'attachments':[{'type':a.get('type','')} for a in post.get('attachments',[])]
                }
        relevant=list(known.values())
        history={'group':GROUP,'items':relevant}
        if history!=posts_history:
            (DATA/'posts.json').write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except Exception as exc:
        errors.append('VK: '+str(exc))
        relevant=list(known.values())
        LOG.warning('VK unavailable: %s',exc)
    processed,notices,applied=apply_changes(entries,relevant)
    # Allow the site to see a fresh check at least once/day, without 96 commits/day.
    old=read_json(DOCS/'schedule.json',{})
    day=now.date().isoformat()
    stamp=old.get('updated_at') or now.isoformat()
    if not stamp.startswith(day):stamp=now.isoformat()
    payload={'group':GROUP,'updated_at':stamp,'source':source,'vk':VK,
             'semester_start':periods[0][0].isoformat(),'semester_end':periods[-1][1].isoformat(),
             'periods':config['periods'],
             'status':'ok' if entries else 'unavailable',
             'source_ok':bool(entries),'source_live':source_live,'vk_ok':vk_ok,
             'entries':processed,'notices':notices,
             'applied_change_links':sorted(set(applied)),
             'warnings':warnings,'errors':errors}
    destination=DOCS/'schedule.json'
    destination.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    LOG.info('Loaded %d ИОЗ-231 lessons, %d applied changes, %d review notices',len(entries),len(applied),len(notices))
    if not entries:raise SystemExit('Не найдено безопасного расписания ИОЗ-231')


if __name__=='__main__':run()
