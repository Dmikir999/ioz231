"""Read-only resolution of language operations against a verified group timetable."""
from __future__ import annotations
import copy
import re
from datetime import date
from scripts import engine as old
from scripts.vk_language import parse_post, QUALIFIED_TAG, GROUP_LINE, group_id, normalize
from scripts.vk_parser_v2 import forms, surname

SLOTS={i:old.PAIR_TIMES[k][0] for i,k in enumerate(('V','VI','VII','VIII'),5)}
ENDS={start:end for start,end in old.PAIR_TIMES.values()}
CONTEXT_FLAGS={'Исходный номер пары не указан',
               'Не указано, является ли занятие новым или перенесённым',
               'Указано только оставшееся занятие; отменяемые пары нужно сверить'}
def slots(op,prefix):
    nums=op[prefix+'_pairs'];times=op[prefix+'_times']
    if any(n not in SLOTS for n in nums):
        raise ValueError('Номер пары не подтверждён сеткой времени ИОЗ-231')
    mapped=[SLOTS[n] for n in nums]
    if mapped and times and set(mapped)!=set(times):
        raise ValueError('Номер пары и время противоречат друг другу')
    return mapped or times

def target_rows(entries,op,day,wanted):
    pool=[e for e in entries if e.get('group')=='ИОЗ-231' and not e.get('cancelled') and e['date']==day]
    teacher_names=op['teachers']
    if teacher_names:
        identities=[]
        for raw in teacher_names:
            names={e.get('teacher','') for e in entries if e.get('group')=='ИОЗ-231' and e.get('teacher') and surname(raw) in forms(e['teacher'])}
            if len(names)!=1:raise ValueError('Преподаватель не найден однозначно в Excel: '+raw)
            identities.append(next(iter(names)))
        pool=[e for e in pool if e.get('teacher') in identities]
        if set(identities)-{e.get('teacher') for e in pool}:return []
    if op.get('kind'):
        needle='лекц' if op['kind']=='lecture' else 'практ'
        pool=[e for e in pool if needle in e.get('kind','').casefold()]
    if op.get('subject_evidence'):
        subjects={x.casefold().strip() for x in op['subject_evidence']}
        pool=[e for e in pool if e.get('subject','').casefold().strip() in subjects]
    if wanted:pool=[e for e in pool if e['time'] in wanted]
    if teacher_names and set(identities)-{e.get('teacher') for e in pool}:return []
    return pool

def resolve_operation(entries,op,url,periods):
    if op.get('subgroup') or 'ИОЗ-231' not in op.get('groups',[]):
        raise ValueError('Не подтверждена принадлежность подгруппе')
    unresolved=[x for x in op['flags'] if x not in CONTEXT_FLAGS]
    if unresolved:raise ValueError('; '.join(unresolved))
    typ=op['type']
    # Unhandled qualifiers must not silently broaden the requested mutation.
    if re.search(r'#|(?:\bкроме\b|\bза\s+исключением\b|\bесли\b|\bвозможно\b|\bпредварительно\b|\bдистанцион\w*|\bонлайн\b)',op['text'],re.I):
        raise ValueError('Дополнительные условия публикации требуют проверки')
    if re.search(r'\bпо\s+дисциплин[еы]\b',op['text'],re.I) and not op.get('subject_evidence'):
        raise ValueError('Не удалось однозначно определить дисциплину')
    # Invalid date tokens must never be treated as an omitted source date.
    for token in old.DATE_RE.finditer(op['text']):
        day,month,year=token.groups()
        try:
            date(int(year or 2026)+(2000 if year and len(year)==2 else 0),int(month),int(day))
        except ValueError:raise ValueError('Некорректная дата в публикации')
    if typ not in ('room','cancel','transfer','scheduled'):raise ValueError('Тип изменения требует отдельной сверки')
    source=op['source_date'];destination=op['destination_date']
    for d in (source,destination):
        if d and periods and not any(a<=date.fromisoformat(d)<=b for a,b in periods):
            raise ValueError('Дата вне учебного периода')
    a=slots(op,'source');b=slots(op,'destination')
    if typ=='transfer' and source==destination and a and set(a)==set(b):raise ValueError('Исходные и новые пары совпадают')
    if typ=='transfer' and any(t not in ENDS for t in b):raise ValueError('Новое время не подтверждено сеткой пар ИОЗ-231')
    if typ in ('transfer','room') and not op['teachers']:raise ValueError('Не указан преподаватель изменения')
    if typ=='cancel' and not op['teachers'] and not op.get('all_day'):raise ValueError('Не указано, чьи занятия отменены')
    if not op['teachers'] and not (a or op.get('all_day')):raise ValueError('Не определена исходная запись')
    if len(op['rooms'])>1:raise ValueError('Не определено распределение аудиторий')
    if any(t not in ENDS for t in a+b):raise ValueError('Время не подтверждено сеткой пар ИОЗ-231')
    room=op['rooms'][0] if op['rooms'] else None
    if typ=='scheduled':
        if not b or not destination or not op['teachers']:raise ValueError('Нельзя однозначно подтвердить занятие')
        matches=target_rows(entries,op,destination,b)
        if not matches or len(matches)!=len(b) or {e['time'] for e in matches}!=set(b) or any(e.get('parallel_id') for e in matches):
            raise ValueError('Заявленное занятие не найдено однозначно в Excel')
        for e in matches:
            if room:old._set_room(e,room)
            e.update(changed=True,change_url=url)
        return len(matches),'Подтверждено существующим Excel; новые занятия не созданы'
    if not source:raise ValueError('Исходная дата отсутствует')
    matches=target_rows(entries,op,source,a)
    if typ=='transfer':
        if not b or not destination:raise ValueError('Не указано новое время')
        if len(op['teachers'])>1:raise ValueError('Несколько преподавателей в переносе')
        if matches and len({(e['subject'],e.get('kind')) for e in matches})>1:raise ValueError('Несколько дисциплин или типов занятия в переносе')
        if not matches:
            # Already reflected, only if the previous slots were explicitly named.
            if not a or len(a)!=len(b) or not op['teachers']:raise ValueError('Исходное занятие не найдено')
            done=target_rows(entries,op,destination,b)
            if len(done)!=len(b) or {e['time'] for e in done}!=set(b) or any(e.get('parallel_id') for e in done):raise ValueError('Перенос не подтверждён в Excel')
            if any(e not in done and not e.get('cancelled') and e['date']==destination and e['time'] in b for e in entries):raise ValueError('Конфликт в новом времени')
            for e,t in zip(sorted(done,key=lambda x:x['time']),a):
                if room:old._set_room(e,room)
                e.update(previous_date=source,previous_time=t,changed=True,change_url=url)
            return len(done),'Перенос уже отражён в Excel'
        if len(matches)!=len(b) or len({e['time'] for e in matches})!=len(matches) or (a and {e['time'] for e in matches}!=set(a)):
            raise ValueError('Число или состав исходных пар неоднозначны')
        if any(e.get('parallel_id') for e in matches):raise ValueError('Параллельные занятия требуют проверки')
        matches.sort(key=lambda x:x['time'])
        for e,t in zip(matches,b):
            if any(other is not e and other not in matches and not other.get('cancelled') and other['date']==destination and other['time']==t for other in entries):
                raise ValueError('Конфликт в новом времени')
        for e,t in zip(matches,b):
            e.update(previous_date=e['date'],previous_time=e['time'],date=destination,weekday=date.fromisoformat(destination).weekday(),time=t,end=ENDS.get(t,''),changed=True,change_url=url)
            if room:old._set_room(e,room)
        return len(matches),'Исходные пары однозначно найдены по преподавателю, дате и числу занятий'
    if not matches or (a and {e['time'] for e in matches}!=set(a)):raise ValueError('Не найдены все исходные занятия')
    if typ in ('room','cancel') and not a and not op.get('all_day') and len(matches)>1 and re.search(r'\b(?:занятие|лекция|практическое занятие|пара)\b',op['text'],re.I):
        raise ValueError('Указано одно занятие, найдено несколько')
    if typ=='room' and not room:raise ValueError('Нет новой аудитории')
    if typ=='cancel' and not op.get('all_day') and any(e.get('parallel_id') for e in matches):raise ValueError('Параллельные занятия требуют проверки')
    if typ=='cancel' and not op.get('all_day') and not op['teachers'] and len({e['time'] for e in matches})!=len(matches):raise ValueError('Неоднозначная отмена')
    for e in matches:
        if typ=='room':old._set_room(e,room)
        else:e['cancelled']=True
        e.update(changed=True,change_url=url)
    return len(matches),'Подтверждено расписанием Excel'

def reconcile(entries,post,periods=None):
    """Atomic per-post, never applies data to disk; no hypothetical group remapping."""
    # The cache only contains relevant public bulletins. Refuse attachments,
    # missing identity, unparsed group scope and partial publications.
    # Explicit target references must not be lost by malformed group headers.
    text=normalize(post.get('text',''))
    mentions_target=old._target(text)
    if post.get('attachments'):
        return copy.deepcopy(entries),{'status':'review' if mentions_target else 'irrelevant','reason':'Вложение требует проверки','operations':[]}
    if post.get('owner_id')!=-70091881 or not isinstance(post.get('id'),int) or not post.get('date'):
        return copy.deepcopy(entries),{'status':'review','reason':'Некорректный источник публикации','operations':[]}
    parsed=parse_post(post);target=[op for op in parsed['operations'] if 'ИОЗ-231' in op['groups']]
    # Never promote course-wide labels, partial subgroup IDs, or a target
    # mentioned only in unparsed prose to the exact group.
    if not target:
        status='review' if old._target(post.get('text','')) else 'irrelevant'
        return copy.deepcopy(entries),{'status':status,'reason':'Нет однозначной операции для ИОЗ-231','operations':[]}
    trial=copy.deepcopy(entries);report=[]
    if any('ИОЗ-231' in x.get('groups',[]) or not x.get('groups') for x in parsed['unparsed']):
        return copy.deepcopy(entries),{'status':'review','reason':'Не разобрана часть публикации','operations':[]}
    failed=False
    url=f"https://vk.com/wall{post.get('owner_id','')}_{post['id']}"
    for op in target:
        try:
            n,reason=resolve_operation(trial,op,url,periods)
            report.append({'type':op['type'],'status':'applicable','affected':n,'reason':reason})
        except ValueError as exc:
            failed=True;report.append({'type':op['type'],'status':'review','reason':str(exc)})
    return (copy.deepcopy(entries) if failed else trial),{'status':'review' if failed else 'applicable','operations':report}
