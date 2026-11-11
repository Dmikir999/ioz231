"""Tiny, dependency-free OOXML reader for the published ИОЗ-231 timetable.

Intentionally extracts *only* column C from the verified sheet '4иоз'.
If the university changes the structure, fail closed rather than display another group.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import io
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

GROUP = 'ИОЗ-231'
NS = {'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
PKG_NS = {'p':'http://schemas.openxmlformats.org/package/2006/relationships'}
DAYS = {'Пн':0,'Вт':1,'Ср':2,'Чт':3,'Пт':4,'Сб':5}
DATE_RX = re.compile(r'(?<!\d)(\d{1,2})\.(\d{2})(?!\d)')
TIME_RX = re.compile(r'(\d{1,2})[.:](\d{2})\s*[-–—]\s*(\d{1,2})[.:](\d{2})')
TYPE_RX = re.compile(r'\((лк|пр)\.\)',re.IGNORECASE)
TEACHER_RX = re.compile(r'\b(?:Доц\.|Проф\.|Ст\.?\s*пр\.)\s*[А-ЯЁ]\.[А-ЯЁ]\.\s*[А-ЯЁ][а-яё-]+',re.IGNORECASE)
ROOM_RX = re.compile(r'Ауд\.\s*(\d{3,5}[А-Яа-я]?)',re.IGNORECASE)
GROUP_NOTE_RX = re.compile(r'для\s+группы\s+ИОЗ\s*[-–—]?\s*(23[12])',re.IGNORECASE)


def _str_cell(cell, shared):
    t = cell.get('t','')
    if t=='inlineStr':
        return ''.join(el.text or '' for el in cell.findall('.//x:is/x:t',NS))
    node=cell.find('x:v',NS)
    if node is None or node.text is None:
        return ''
    if t=='s':
        return shared[int(node.text)]
    return node.text


def _sheet_rows(blob:bytes, sheet_name='4иоз'):
    with ZipFile(io.BytesIO(blob)) as z:
        book=ET.fromstring(z.read('xl/workbook.xml'))
        rel_id=None
        for el in book.findall('.//x:sheets/x:sheet',NS):
            if el.get('name')==sheet_name:
                rel_id=el.get('{%s}id'%NS['r']);break
        if not rel_id:
            raise ValueError(f'В таблице отсутствует проверенный лист {sheet_name!r}; формат изменён')
        relationships=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target=None
        for el in relationships.findall('p:Relationship',PKG_NS):
            if el.get('Id')==rel_id:
                target=el.get('Target');break
        if not target:raise ValueError('Не найден XML листа 4иоз')
        full_path=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        if '..' in Path(full_path).parts:raise ValueError('Некорректная ссылка XML')
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in strings.findall('x:si',NS):
                shared.append(''.join(t.text or '' for t in si.findall('.//x:t',NS)))
        root=ET.fromstring(z.read(full_path))
        rows={}
        for r in root.findall('.//x:sheetData/x:row',NS):
            num=int(r.get('r'))
            cells={}
            for c in r.findall('x:c',NS):
                address=c.get('r') or ''
                col=re.match(r'[A-Z]+',address)
                if col:cells[col.group()]=_str_cell(c,shared)
            rows[num]=cells
        return rows


def _norm(text):
    return ' '.join(str(text).split()).strip()


def _segments(text):
    # The university separates alternatives within one cell by a spaced slash.
    return [part.strip() for part in re.split(r'\s+/\s+',_norm(text)) if part.strip()]


def _expand_segment(segment, day_number, start, end, source_row, warnings, periods):
    types=list(TYPE_RX.finditer(segment))
    if not types:
        if DATE_RX.search(segment):warnings.append(f'Строка {source_row}: не определён тип пары; пропущено')
        return []
    subject=_norm(segment[:types[0].start()]).rstrip(' ,.;')
    if not subject or subject.startswith('для группы'):
        warnings.append(f'Строка {source_row}: не удалось определить дисциплину')
        return []
    teacher=TEACHER_RX.search(segment)
    room=ROOM_RX.search(segment)
    kind={'лк':'Лекция','пр':'Практика'}
    result=[]
    for idx,t in enumerate(types):
        section=segment[t.end():types[idx+1].start() if idx+1<len(types) else len(segment)]
        # Teacher name belongs to the whole slash-delimited segment, not the date list.
        # A note 'для группы ИОЗ-232' excludes only dates of this lesson kind.
        notes=GROUP_NOTE_RX.findall(section)
        if notes and '231' not in notes:
            continue
        for m in DATE_RX.finditer(section):
            dd,mm=map(int,m.groups())
            candidates = []
            for first, last in periods:
                for year in range(first.year, last.year + 1):
                    try:
                        candidate = date(year, mm, dd)
                    except ValueError:
                        continue
                    if first <= candidate <= last:
                        candidates.append(candidate)
            if len(candidates) != 1 or candidates[0].weekday() != day_number:
                warnings.append(f'Строка {source_row}: проверьте дату {m.group(0)}, учебный период и день недели')
                continue
            when = candidates[0]
            item={'group':GROUP,'date':when.isoformat(),'weekday':day_number,'time':start,'end':end,
                  'subject':subject,'kind':kind[t.group(1).lower()],
                  'teacher':_norm(teacher.group(0)) if teacher else '',
                  'room':room.group(1) if room else '',
                  'source':'base','source_sheet':'4иоз','source_row':source_row}
            key='|'.join([item['date'],item['time'],item['subject'],item['kind'],str(source_row)])
            item['id']=sha256(key.encode()).hexdigest()[:14]
            result.append(item)
    return result


def parse_xlsx(blob:bytes, sheet, periods):
    rows=_sheet_rows(blob, sheet)
    if _norm(rows.get(7,{}).get('C','')).upper().replace(' ','') != GROUP:
        raise ValueError('Ожидаемая группа ИОЗ-231 не обнаружена в колонке C листа 4иоз')
    if _norm(rows.get(7,{}).get('D','')).upper()!='ИОЗ-232':
        raise ValueError('Соседняя группа ИОЗ-232 не найдена в колонке D: формат таблицы изменился')
    day=None;start=end=''
    lessons=[];warnings=[]
    for rowno in sorted(rows):
        if rowno<8:continue
        row=rows[rowno]
        day_text=_norm(row.get('A','')).rstrip('.')
        if day_text in DAYS:
            day=DAYS[day_text]; start=end=''
        time_text=_norm(row.get('B',''))
        m=TIME_RX.search(time_text)
        if m:
            sh,sm,eh,em=map(int,m.groups())
            if sh>23 or eh>23 or sm>59 or em>59:raise ValueError(f'Неизвестный формат времени в строке {rowno}')
            start=f'{sh:02d}:{sm:02d}';end=f'{eh:02d}:{em:02d}'
        content=_norm(row.get('C',''))
        if not content or content in ('УЧЕБНЫЕ ГРУППЫ','ИОЗ-231'):
            continue
        if day is None or not start:
            warnings.append(f'Строка {rowno}: заполненная ячейка без дня/времени; пропущено')
            continue
        row_lessons = []
        for seg in _segments(content):
            items = _expand_segment(seg, day, start, end, rowno, warnings, periods)
            for item in items:
                item['source_sheet'] = sheet
            row_lessons.extend(items)
        lessons.extend(row_lessons)
        # Only this confirmed elective is shared with the neighbouring column.
        shared = {(e['date'], e['kind']): e for e in row_lessons
                  if e['subject'].casefold() == 'кв образовательное пространство столичного мегаполиса'}
        if shared:
            for seg in _segments(row.get('D', '')):
                title = TYPE_RX.split(seg, maxsplit=1)[0].strip(' ,.;')
                if title.casefold() != 'кв организация проектной деятельности обучающихся при изучении обществознания':
                    continue
                for other in _expand_segment(seg, day, start, end, rowno, warnings, periods):
                    first = shared.get((other['date'], other['kind']))
                    if first:
                        other['source_sheet'] = sheet
                        other['parallel_id'] = first['parallel_id'] = first['id']
                        lessons.append(other)
    unique={}
    for e in lessons:
        # An identical lesson can be repeated in the XLSX only because of technical overlap;
        # don't duplicate cards for one subject and time.
        key=(e['date'],e['time'],e['subject'],e['kind'])
        if key in unique:
            warnings.append(f'Повтор занятия на {e["date"]} в {e["time"]}: {e["subject"]} (строки {unique[key]["source_row"]}, {e["source_row"]})')
            continue
        unique[key]=e
    output=sorted(unique.values(),key=lambda e:(e['date'],e['time'],e['subject']))
    if len(output)<40:raise ValueError(f'Найдено слишком мало занятий ({len(output)}); импорт остановлен для безопасности')
    return output,warnings
