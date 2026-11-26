"""Conservative VK bulletin interpreter (shadow mode; never writes schedule files).

A recognized operation and a safely applicable operation are distinct. Preserve
group scope, explicit evidence and lesson identity. Never guess a conflicting slot.
"""
from __future__ import annotations
import copy
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from scripts import engine as old

GROUP = 'ИОЗ-231'
# All tagged groups delimit scope, not just other ИОЗ groups.
GROUP_TAG = re.compile(r'#([А-ЯЁA-Z][А-ЯЁA-Z0-9_-]*?)[ _–—-]?(\d{3})(?!\d)', re.I)
GROUP_HEAD = re.compile(r'^\s*[❗‼❕!💥⚡️\s]*(?P<groups>(?:#[А-ЯЁA-Z][\w-]*\d{3}|И[ОO0][З3][ _–—-]?\d{3})(?:\s*[,;/]\s*(?:#[А-ЯЁA-Z][\w-]*\d{3}|И[ОO0][З3][ _–—-]?\d{3}))*)\s*[-–—:]\s*(?P<body>.*)$', re.I)
PAIR = r'(?:VIII|VII|VI|V|[5-8])'
PAIR_EXPR = re.compile(r'(?<![\w])(?P<first>'+PAIR+r')(?:\s*[-–—]\s*(?P<last>'+PAIR+r'))?\s*(?:-?(?:я|й|ю|ой|ые|ых)\s+)?пар(?:а|у|е|ы|ах|ой)?\b', re.I)
PAIR_NUMBER = {'V':5,'VI':6,'VII':7,'VIII':8}
SLOTS = {i:old.PAIR_TIMES[k] for k,i in PAIR_NUMBER.items()}
CLOCK = re.compile(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)')
ROOM = re.compile(r'\b(?:ауд(?:итори[яиюе]|\.)?|каб(?:инет[еа]|\.)?)\s*№?\s*(\d{3,5}[А-Яа-я]?)\b',re.I)
TRANSFER = re.compile(r'перен[её]с\w*|перенос|состо[ия]\w*|пройд[её]т|пройдут|вместо',re.I)
CANCEL = re.compile(r'отмен\w*|не\s+состо[ия]\w*|не\s+будет',re.I)
ROOM_WORD = re.compile(r'изменени[ея]\s+аудиторий|смен[аы]\s+аудитори|будет\s+в\s+ауд|пройд[её]т\s+в\s+ауд|пройдут\s+в\s+ауд|занятия?\s+.+\s+в\s+ауд',re.I)
RANK = re.compile(r'(?:доц\.|проф\.|ст\.\s*пр\.|преподавател[ья]|асс\.)\s*(?:[А-ЯЁ]\.\s*){0,2}([А-ЯЁ][А-ЯЁа-яё-]+)',re.I)
ALL_DAY = re.compile(r'\b(?:все|весь)\s+(?:занятия|пары|учебный день)\b',re.I)
SUBSTITUTE = re.compile(r'вместо\s+(?:дисциплины|предмета)\s*[«"]([^»"]+)[»"]\s+(?:состоится|будет|пройд[её]т)\s*[«"]([^»"]+)[»"]',re.I)
TEACHER_SUB = re.compile(r'вместо\s+(?:преподавателя\s+)?(?:доц\.|проф\.|ст\.\s*пр\.)?\s*([А-ЯЁ][А-ЯЁа-яё-]+)\s+занятие\s+провед[её]т\s+(?:доц\.|проф\.|ст\.\s*пр\.)?\s*([А-ЯЁ][А-ЯЁа-яё-]+)',re.I)

def norm(text):
    return re.sub(r'[ \t\u00a0]+',' ',unicodedata.normalize('NFKC',str(text or ''))).strip()

def dates(text, stamp):
    ref=datetime.fromtimestamp(stamp or datetime.now(old.TZ).timestamp(),old.TZ).date()
    result=set(old.parse_dates(text,ref.year))
    for word,delta in [('сегодня',0),('завтра',1),('послезавтра',2)]:
        if re.search(r'\b'+word+r'\b',text,re.I):result.add((ref+timedelta(days=delta)).isoformat())
    return sorted(result)

def times(text):
    result=[]
    for m in PAIR_EXPR.finditer(text):
        a=PAIR_NUMBER.get(m['first'].upper(),None)
        b=PAIR_NUMBER.get((m['last'] or m['first']).upper(),None)
        a=a if a is not None else int(m['first'])
        b=b if b is not None else int(m['last'] or m['first'])
        if b<a:raise ValueError('Обратный диапазон пар')
        result.extend(SLOTS[x][0] for x in range(a,b+1))
    result.extend(f'{int(h):02d}:{m}' for h,m in CLOCK.findall(text))
    return sorted(set(result))

def surname(value):
    return re.sub(r'ё','е',value.casefold().split()[-1].rsplit('.',1)[-1]) if value else ''

def forms(value):
    s=surname(value);out={s}
    if s.endswith(('ов','ев','ин','ын','ий','ский','цкий')):
        if s.endswith('ий'):out.add(s[:-2]+'ого')
        else:out.add(s+'а')
    if s.endswith(('ова','ева','ина','ына')):out.add(s[:-1]+'ой')
    if s.endswith('ая'):out.add(s[:-2]+'ой')
    if s.endswith(('ко','ман','ер','ель')):out.add(s+'а')
    return out

def mentions(text,name):
    return any(re.search(r'(?<![а-яё])'+re.escape(f)+r'(?![а-яё])',text.casefold().replace('ё','е')) for f in forms(name) if f)

def scopes(post):
    """Only explicit target scope can authorize mutation; header supplies context."""
    text=norm(post.get('text'))
    if not old._target(text):return []
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    header=[];out=[];scope=None;buf=[]
    def flush():
        if scope and buf:out.append((' '.join(header), '\n'.join(buf)))
    for line in lines:
        m=GROUP_HEAD.match(line)
        if m:
            flush();scope=old._target(m['groups']);buf=[m['body']]
        elif GROUP_TAG.search(line) or old._target(line):
            flush()
            # A line without a delimiter is safe only with a single group or
            # a leading group list. Later tags make its scope ambiguous.
            tags=list(GROUP_TAG.finditer(line))
            if tags and any(x.start()>line.find('—') for x in tags) and '—' in line:
                scope=False;buf=[]
            else:
                scope=old._target(line) and (len(tags)<=1 or not tags)
                buf=[line] if scope else []
        elif scope is None:header.append(line)
        elif scope:buf.append(line)
    flush()
    return out

def clauses(body):
    # Periods within dates and titles must not split a statement.
    return [x.strip() for x in re.split(r';|\n+|(?<=\.)\s+(?=(?:Практ|Лекц|Заняти|Пара|Все\s+заняти|Вместо|Отмена|Перенос))',body,flags=re.I) if x.strip()]

def known_teachers(entries,text):
    return {e.get('teacher','') for e in entries if e.get('teacher') and mentions(text,e['teacher'])}

def room_value(text):
    values=set(ROOM.findall(text))
    if len(values)>1:raise ValueError('Несколько аудиторий без однозначного назначения')
    return next(iter(values),None)

def parse_clause(header,text,post,entries):
    stamp=post.get('date',0)
    context=header+' '+text
    all_dates=dates(text,stamp) or dates(header,stamp)
    teacher_names=known_teachers(entries,text)
    if len(teacher_names)>1 and not TEACHER_SUB.search(text):
        raise ValueError('Несколько преподавателей в одном изменении')
    teacher=next(iter(teacher_names),None)
    if RANK.search(text) and not teacher and not TEACHER_SUB.search(text):
        raise ValueError('Преподаватель не найден в Excel')
    subjects={e['subject'] for e in entries if e.get('subject') and e['subject'].casefold() in text.casefold()}
    subject=next(iter(subjects),None) if len(subjects)==1 else None
    kind='лекц' if re.search(r'\bлекц',text,re.I) else 'практ' if re.search(r'\bпракт|семинар',text,re.I) else None
    op=dict(teacher=teacher,subject=subject,kind=kind,room=room_value(text),text=text)
    sub=SUBSTITUTE.search(text);ts=TEACHER_SUB.search(text)
    if sub or ts:
        op['kind']=None
        if len(all_dates)!=1:raise ValueError('Нет одной даты замены')
        op.update(type='replace',date=all_dates[0],times=times(text))
        if sub:op.update(subject=sub[1],new_subject=sub[2])
        else:
            originals=known_teachers(entries,ts[1]);new=known_teachers(entries,ts[2])
            if len(originals)!=1 or len(new)!=1:raise ValueError('Неоднозначная замена преподавателя')
            op.update(teacher=next(iter(originals)),new_teacher=next(iter(new)))
        return op
    if CANCEL.search(text):
        if TRANSFER.search(text) and not re.search(r'не\s+состо',text,re.I):raise ValueError('Отмена и перенос одновременно')
        if len(all_dates)!=1:raise ValueError('Нет одной даты отмены')
        slots=times(text);broad=bool(ALL_DAY.search(text))
        if not slots and not teacher and not subject and not broad:raise ValueError('Не указан объём отмены')
        return dict(op,type='cancel',date=all_dates[0],times=slots,broad=broad)
    # Transfer: explicit source/destination halves, preserving order rather than sorting dates.
    if TRANSFER.search(text):
        split=re.search(r'\bс\s+(.+?)\s+на\s+(.+)',text,re.I)
        if not split:
            split=re.search(r'\bвместо\s+(.+?)\s+(?:занятие\s+)?(?:состоится|пройд[её]т|будет)\s+(.+)',text,re.I)
        if not split and len(all_dates)==2:
            split=re.search(r'(.+?)\b(?:перен[её]с\w*\s+на|состоится|пройд[её]т)\s+(.+)',text,re.I)
        if split:
            left,right=split[1],split[2];ld,rd=dates(left,stamp),dates(right,stamp)
            if not ld and len(all_dates)==1:ld=all_dates
            if not rd and len(ld)==1:rd=ld
            if len(ld)!=1 or len(rd)!=1:raise ValueError('Не определены исходная и новая даты')
            for fragment,when in [(left,ld[0]),(right,rd[0])]:
                for index,word in enumerate(old.WEEKDAYS):
                    if re.search(r'\b'+word+r'\b',fragment,re.I) and date.fromisoformat(when).weekday()!=index:
                        raise ValueError('Дата противоречит дню недели')
            new=times(right);previous=times(left)
            if not new:raise ValueError('Не указано новое время/номер пары')
            if not previous and not teacher and not subject:raise ValueError('Не определена исходная пара')
            return dict(op,type='transfer',date=ld[0],new_date=rd[0],times=previous,new_times=new)
    if op['room'] and (ROOM_WORD.search(context) or re.search(r'измен|смен',context,re.I)):
        if len(all_dates)!=1:raise ValueError('Нет одной даты смены аудитории')
        slots=times(text)
        if not slots and not teacher and not subject:raise ValueError('Не определены занятия для смены аудитории')
        return dict(op,type='room',date=all_dates[0],times=slots)
    raise ValueError('Формулировка не поддержана или данных недостаточно')

def same_subject(a,b):
    return norm(a).casefold()==norm(b).casefold()

def matches(entry,op,when,slots):
    return (entry.get('group',GROUP)==GROUP and not entry.get('cancelled') and entry.get('date')==when
            and (not slots or entry.get('time') in slots)
            and (not op.get('teacher') or entry.get('teacher')==op['teacher'])
            and (not op.get('subject') or same_subject(entry.get('subject',''),op['subject']))
            and (not op.get('kind') or op['kind'] in entry.get('kind','').casefold()))

def apply_operation(entries,op,url,periods):
    when=op['date'];new_date=op.get('new_date',when)
    if periods and any(not any(a<=date.fromisoformat(d)<=b for a,b in periods) for d in (when,new_date)):
        raise ValueError('Дата за пределами учебного периода')
    found=[e for e in entries if matches(e,op,when,op['times'])]
    if op['type']=='transfer':
        dest=op['new_times']
        # Already reflected in Excel, only if the source is absent and teacher/subject identifies the destination.
        if not found and (op['teacher'] or op['subject']) and op['times'] and len(op['times'])==len(dest):
            already=[e for e in entries if matches(e,op,new_date,dest)]
            if len(already)==len(dest) and {e['time'] for e in already}==set(dest):
                for e,t in zip(sorted(already,key=lambda x:x['time']),op['times']):
                    if op['room']:old._set_room(e,op['room'])
                    e.update(previous_date=when,previous_time=t,changed=True,change_url=url)
                return len(already)
        if len(found)!=len(dest) or not found:raise ValueError('Число исходных и новых пар не совпадает')
        if op['times'] and {e['time'] for e in found}!=set(op['times']):raise ValueError('Не найдены все исходные пары')
        if len({e['time'] for e in found})!=len(found):raise ValueError('Исходные пары неоднозначны')
        found.sort(key=lambda e:e['time'])
        # Validate all destinations before mutating any record.
        for e,t in zip(found,dest):
            if e['date']==new_date and e['time']==t:raise ValueError('Исходная и новая пары совпадают')
            if any(other is not e and other not in found and not other.get('cancelled') and other['date']==new_date and other['time']==t for other in entries):
                raise ValueError('На новом времени уже есть занятие')
        for e,t in zip(found,dest):
            previous=e['time'];e.update(previous_date=when,previous_time=previous,date=new_date,weekday=date.fromisoformat(new_date).weekday(),time=t,end=next((end for start,end in SLOTS.values() if start==t),''))
            if op['room']:old._set_room(e,op['room'])
    else:
        if not found:raise ValueError('Не найдены подходящие занятия')
        if op['times'] and {e['time'] for e in found}!=set(op['times']):raise ValueError('Не найдены все указанные пары')
        if not op.get('broad') and len({e['time'] for e in found})!=len(found):raise ValueError('Есть параллельные занятия; уточните предмет')
        if op['type']=='replace' and len(found)!=1:raise ValueError('Замена должна соответствовать одной паре')
        for e in found:
            if op['type']=='room':old._set_room(e,op['room'])
            elif op['type']=='cancel':e['cancelled']=True
            elif op['type']=='replace':
                if op.get('new_teacher'):e.update(previous_teacher=e.get('teacher'),teacher=op['new_teacher'])
                if op.get('new_subject'):e.update(previous_subject=e.get('subject'),subject=op['new_subject'])
                if op['room']:old._set_room(e,op['room'])
    for e in found:e.update(changed=True,change_url=url)
    return len(found)

def analyze(entries,posts,periods=None):
    schedule=copy.deepcopy(entries);report=[]
    # Newest revision of each bulletin only; repeatable rebuild from original Excel.
    unique={}
    for post in posts:
        key=(post.get('owner_id'),post.get('id'))
        if not isinstance(key[1],int):continue
        if key not in unique or post.get('edited',0)>=unique[key].get('edited',0):unique[key]=post
    for post in sorted(unique.values(),key=lambda p:(p.get('date',0),p.get('id',0))):
        if not old._target(post.get('text','')):continue
        url=f"https://vk.com/wall{post.get('owner_id','')}_{post['id']}"
        item=dict(post_id=post['id'],url=url,operations=[],status='review')
        report.append(item)
        if post.get('attachments'):
            item['reason']='Вложения требуют OCR/проверки; без подтверждения не применять';continue
        groups=scopes(post)
        if not groups:item['reason']='Не удалось безопасно выделить группу';continue
        trial=copy.deepcopy(schedule);failed=False
        for header,body in groups:
            for text in clauses(body):
                result={'text':text,'status':'review'}
                item['operations'].append(result)
                try:
                    op=parse_clause(header,text,post,trial);result.update(operation=op,status='recognized')
                    result['affected']=apply_operation(trial,op,url,periods);result['status']='applicable'
                except ValueError as exc:
                    result['reason']=str(exc);failed=True
        # Atomic per-post: no half-applied transfer or compound bulletin.
        if not failed and item['operations']:
            schedule=trial;item['status']='applicable'
        else:item['reason']='Публикация не применена целиком: требуется проверка'
    schedule.sort(key=lambda e:(e['date'],e['time'],e.get('subject','')))
    return schedule,report

def main():
    root=Path(__file__).resolve().parent.parent
    base=json.loads((root/'data/base.json').read_text(encoding='utf-8'))
    posts=json.loads((root/'data/posts.json').read_text(encoding='utf-8'))['items']
    periods=[(date.fromisoformat(a),date.fromisoformat(b)) for a,b in base['semester']['periods']]
    _,report=analyze(base['entries'],posts,periods)
    print(json.dumps({'mode':'shadow','total':len(report),'applicable':sum(x['status']=='applicable' for x in report),'posts':report},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
