"""VK bulletin language parser. Extract evidence independently of the timetable.

This module deliberately never writes or changes a timetable. Group scope,
pair numbers, missing fields and conflicting weekdays are preserved for a
separate safe reconciliation stage. No times are assumed for pairs I-IV.
"""
from __future__ import annotations
import re
import unicodedata
from datetime import date, datetime, timedelta
from scripts import engine as old

GROUP_ID=r'[А-ЯЁA-Z]{2,}[ _-]?\d{1,3}(?:\.\d+)?[мМ]?'
TAG=re.compile(r'#(?P<id>'+GROUP_ID+r')',re.I)
GROUP_LINE=re.compile(r'^\s*Группа\s+(?P<id>'+GROUP_ID+r')\s*:?\s*$',re.I)
LEADING=re.compile(r'^[^\w#]*?(?P<tags>#'+GROUP_ID+r'(?:\s*,\s*#'+GROUP_ID+r')*)(?:\s*,?\s*(?P<sub>подгруппа\s+\d+|КВ))?\s*[—–-]\s*(?P<body>.+)$',re.I)
PAIR_NUMBER={k:i for i,k in enumerate(('I','II','III','IV','V','VI','VII','VIII'),1)}
PAIR=r'(?:VIII|VII|VI|IV|III|II|I|V|[1-8])'
PAIR_RX=re.compile(r'(?<![\w])('+PAIR+r')(?:\s*[-–—]\s*('+PAIR+r'))?\s*(?:-?(?:я|й|ю|ой|ые|ых)\s+)?пар(?:а|у|е|ы|ах|ой)?\b',re.I)
CLOCK=re.compile(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)')
RANK=r'(?:доц\.|проф\.|ст\.\s*(?:преп\.|пр\.)|асс\.|преподавател[ья])'
NAME=r'[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)*'
TEACHER=re.compile(RANK+r'\s*(?:[А-ЯЁ]\.\s*){0,2}('+NAME+r')',re.I)
BARE_TEACHER=re.compile(r'\b(?:занятия?|лекция|практика)\s+('+NAME+r')\s+(?:пройдут|пройд[её]т|в\s+ауд|перен[её]с|отмен)',re.I)
ROOMS=re.compile(r'\b(?:ауд(?:итори[яиюе]|\.|ории)?|каб(?:инет[еа]|\.)?)\s*№?\s*(\d{3,5}[А-Яа-я]?(?:\s*(?:,|и|/)\s*\d{3,5}[А-Яа-я]?)*)(?!\d)',re.I)
MOVE=re.compile(r'\bперен[её]с\w*|\bперенос\b',re.I)
SCHEDULED=re.compile(r'назначен[оыа]|состо[ия]\w*|пройд[её]т|пройдут|будет|будут',re.I)
CANCEL=re.compile(r'отмен\w*|не\s+состо[ия]\w*|не\s+будет',re.I)
DAY_NAMES=(
    ('понедельник','понедельника'),('вторник','вторника','вторинка'),
    ('среда','среду','среды'),('четверг','четверга'),
    ('пятница','пятницу','пятницы'),('суббота','субботу','субботы'),
    ('воскресенье','воскресенья'))
SENTENCE=re.compile(r';|\n+|(?<=\.)(?<!практ\.)(?<!лекц\.)(?<!доц\.)(?<!проф\.)(?<!ст\.пр\.)(?<!ст\. пр\.)(?<!преп\.)(?<!ауд\.)\s+(?=(?:Практ|Лекц|Заняти|Пара|Все\s+заняти|Вместо|Отмена|Перенос))',re.I)

def normalize(text):
    return unicodedata.normalize('NFKC',text or '').replace('\u00a0',' ')

def group_id(value):
    return re.sub(r'[ _-]+','-',value.upper())

def pair_numbers(text):
    out=[]
    for m in PAIR_RX.finditer(text):
        def number(v):return int(v) if v.isdigit() else PAIR_NUMBER[v.upper()]
        a,b=number(m[1]),number(m[2] or m[1])
        if a>b:raise ValueError('Обратный диапазон пар')
        out.extend(range(a,b+1))
    return list(dict.fromkeys(out))

def time_values(text):
    return list(dict.fromkeys(f'{int(h):02d}:{m}' for h,m in CLOCK.findall(text)))

def date_values(text,stamp):
    ref=datetime.fromtimestamp(stamp,old.TZ).date()
    out=old.parse_dates(text,ref.year)
    for word,delta in [('сегодня',0),('завтра',1),('послезавтра',2)]:
        if re.search(r'\b'+word+r'\b',text,re.I):out.append((ref+timedelta(days=delta)).isoformat())
    return list(dict.fromkeys(out))

def date_one(text,stamp,flags):
    ds=date_values(text,stamp)
    if len(ds)>1:flags.append('Несколько дат без однозначного назначения');return None
    if not ds:return None
    value=ds[0]
    for i,words in enumerate(DAY_NAMES):
        if any(re.search(r'\b'+w+r'\b',text,re.I) for w in words) and date.fromisoformat(value).weekday()!=i:
            flags.append('День недели противоречит дате: '+value)
    return value

def sections(text):
    """Retain original groups including course-wide tags, subgroup IDs and headings."""
    header=[];groups=[];sub=None;out=[]
    for line in normalize(text).splitlines():
        line=line.strip()
        if not line:continue
        m=LEADING.match(line)
        if m:
            groups=[group_id(t['id']) for t in TAG.finditer(m['tags'])]
            sub=m['sub'];out.append((groups[:],sub,' '.join(header),m['body']));continue
        m=GROUP_LINE.match(line)
        if m:
            groups=[group_id(m['id'])];sub=None;continue
        if line.upper().startswith('ВНИМАНИЕ') and TAG.search(line):
            groups=[group_id(t['id']) for t in TAG.finditer(line)];sub=None;continue
        if not groups:
            header.append(line);continue
        if TAG.search(line):
            # Do not silently inherit a previous group's scope.
            groups=[group_id(t['id']) for t in TAG.finditer(line)];sub=None
        out.append((groups[:],sub,' '.join(header),line))
    return out

def parse_statement(text,header,stamp):
    flags=[]
    names=list(dict.fromkeys(m[1] for m in TEACHER.finditer(text)))
    if not names:
        bare=BARE_TEACHER.search(text)
        if bare:names=[bare[1]]
    rooms=[]
    for m in ROOMS.finditer(text):
        rooms.extend(re.findall(r'\d{3,5}[А-Яа-я]?',m[1]))
    rooms=list(dict.fromkeys(rooms))
    if len(names)>1 or len(rooms)>1:flags.append('Распределение преподавателей, пар и аудиторий требует сверки')
    kind='lecture' if re.search(r'\bлекц',text,re.I) else 'practice' if re.search(r'\bпракт|семинар',text,re.I) else None
    result=dict(teachers=names,rooms=rooms,kind=kind,source_date=None,source_pairs=[],source_times=[],destination_date=None,destination_pairs=[],destination_times=[],flags=flags)
    def source(fragment):
        result.update(source_date=date_one(fragment,stamp,flags),source_pairs=pair_numbers(fragment),source_times=time_values(fragment))
    def destination(fragment):
        result.update(destination_date=date_one(fragment,stamp,flags),destination_pairs=pair_numbers(fragment),destination_times=time_values(fragment))
    if CANCEL.search(text):
        result['type']='cancel';source(text)
        if not result['source_date']:result['source_date']=date_one(header,stamp,flags)
        result['all_day']=bool(re.search(r'\bвсе\s+(?:пары|занятия)',text,re.I))
        if MOVE.search(text):flags.append('Одновременно отмена и перенос')
    elif MOVE.search(text):
        result['type']='transfer'
        m=re.search(r'\bсо?\s+(.+?)\s+на\s+(.+)',text,re.I)
        if not m:raise ValueError('Не определены части переноса')
        source(m[1]);destination(m[2])
        if not result['source_date'] and result['destination_date'] and result['source_pairs']:
            result['source_date']=result['destination_date']
            result['same_day_inferred']=True
        if not result['destination_date'] and result['source_date'] and result['destination_pairs']:
            result['destination_date']=result['source_date']
            result['same_day_inferred']=True
    elif re.search(r'\bвместо\s+(?:дисциплины|предмета)\b',text,re.I):
        result['type']='subject_replacement';source(text)
        result['subjects']=re.findall(r'[«"]([^»"]+)[»"]',text)
        if len(result['subjects'])!=2:flags.append('Не определены обе дисциплины')
    elif re.search(r'\bвместо\b.*\bпровед[её]т',text,re.I):
        result['type']='teacher_replacement';source(text)
        if len(names)!=2:flags.append('Не определены оба преподавателя')
    elif SCHEDULED.search(text) and re.search(r'\bвместо\b',text,re.I):
        result['type']='transfer'
        before,after=re.split(r'\bвместо\b',text,maxsplit=1,flags=re.I)
        source(after);destination(before)
    elif SCHEDULED.search(text) and re.search(r'\bтолько\b',text,re.I):
        result['type']='restriction';destination(text)
        flags.append('Указано только оставшееся занятие; отменяемые пары нужно сверить')
    elif re.search(r'изменени[ея]\s+аудиторий',header,re.I) or (rooms and not pair_numbers(text) and re.search(r'в\s+ауд|аудитор',text,re.I)):
        result['type']='room';source(text)
        if not result['source_date']:result['source_date']=date_one(header,stamp,flags)
        if not rooms:flags.append('Не указана аудитория')
    elif SCHEDULED.search(text) and (pair_numbers(text) or time_values(text)):
        result['type']='scheduled';destination(text)
        flags.append('Не указано, является ли занятие новым или перенесённым')
    else:
        raise ValueError('Не определён тип изменения')
    if result['type']=='transfer':
        if not result['source_date']:flags.append('Исходная дата не указана')
        if not result['source_pairs'] and not result['source_times']:flags.append('Исходный номер пары не указан')
        if not result['destination_date']:flags.append('Новая дата не указана')
        if not result['destination_pairs'] and not result['destination_times']:flags.append('Новый номер пары не указан')
    elif result['type'] in ('scheduled','restriction'):
        if not result['destination_date']:flags.append('Дата не указана')
    elif not result['source_date']:flags.append('Дата не указана')
    if not names and result['type']=='room' and not result['source_pairs'] and not result['source_times']:
        flags.append('Преподаватель или номер пары не указан')
    result['flags']=list(dict.fromkeys(flags))
    return result

def parse_post(post):
    operations=[];unparsed=[]
    for groups,sub,header,body in sections(post.get('text','')):
        for clause in SENTENCE.split(body):
            clause=clause.strip()
            if not clause:continue
            try:
                op=parse_statement(clause,header,post['date'])
                op.update(groups=groups,subgroup=sub,text=clause)
                operations.append(op)
            except ValueError as exc:
                unparsed.append({'groups':groups,'text':clause,'reason':str(exc)})
    # Preserve attachments as an explicit unresolved source.
    if post.get('attachments'):unparsed.append({'reason':'Вложение требует отдельного распознавания'})
    return dict(post_id=post.get('id'),operations=operations,unparsed=unparsed,
                status='recognized' if operations and not unparsed else 'review',
                requires_review=bool(unparsed or not operations or any(x['flags'] for x in operations)))
