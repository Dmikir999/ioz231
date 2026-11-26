"""Shadow parser regression tests: synthetic examples, never published data."""
import copy
import json
import unittest
from datetime import date, datetime
from pathlib import Path
from scripts.vk_parser_v2 import analyze, times, dates
from scripts.engine import TZ

STAMP=int(datetime(2026,11,25,12,tzinfo=TZ).timestamp())
PERIODS=[(date(2026,11,3),date(2026,12,30))]
def lesson(day,time,teacher='Доц. И.А. Нидерман',subject='Методика обучения истории',kind='Лекция',room='3406'):
    return dict(group='ИОЗ-231',date=day,time=time,end='',teacher=teacher,subject=subject,kind=kind,room=room,weekday=date.fromisoformat(day).weekday())
def post(text,**extra):
    return dict(id=1,owner_id=-70091881,date=STAMP,text=text,**extra)
def evaluate(entries,text,**extra):
    return analyze(entries,[post(text,**extra)],PERIODS)

class ShadowParserTests(unittest.TestCase):
    def test_pair_notations(self):
        cases={'V пара':['15:40'],'VI пару':['17:10'],'VII пары':['18:40'],'VIII паре':['20:10'],'7-я пара':['18:40'],'8-й паре':['20:10'],'VII–VIII пары':['18:40','20:10'],'V-VIII пары':['15:40','17:10','18:40','20:10'],'15:40':['15:40']}
        for phrase,expected in cases.items():
            with self.subTest(phrase=phrase):self.assertEqual(times(phrase),expected)
    def test_transfer_matrix(self):
        forms=['#ИОЗ_231 — занятие доц. Нидерман перенесено с {source} 11.12 на {dest} 27.11.',
               '#ИОЗ-231 — занятие доц. Нидерман перенесено с {source} 11 декабря на {dest} 27 ноября.',
               '#ИОЗ_231, #ИОЗ_232 — занятие доц. Нидерман перенесено с {source} 11.12 на {dest} 27.11.']
        slots=[('V пары','15:40'),('VI пары','17:10'),('VII пары','18:40'),('VIII пары','20:10'),('5-й пары','15:40'),('6-й пары','17:10'),('7-й пары','18:40'),('8-й пары','20:10')]
        for template in forms:
            for source,old in slots:
                for dest,new in slots:
                    with self.subTest(template=template,source=source,dest=dest):
                        base=[lesson('2026-12-11',old)]
                        result,report=evaluate(base,template.format(source=source,dest=dest))
                        self.assertEqual(report[0]['status'],'applicable',report)
                        self.assertEqual((result[0]['date'],result[0]['time']),('2026-11-27',new))
                        self.assertEqual(base[0]['date'],'2026-12-11')
    def test_multiple_pairs(self):
        base=[lesson('2026-12-11',t) for t in ('18:40','20:10')]
        result,report=evaluate(base,'#ИОЗ_231 — занятия доц. Нидерман перенесены с VII-VIII пары 11.12 на V-VI пары 27.11, ауд. 3210.')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertEqual([(e['date'],e['time'],e['room']) for e in result],[('2026-11-27','15:40','3210'),('2026-11-27','17:10','3210')])
    def test_room_header(self):
        base=[lesson('2026-11-27','15:40')]
        result,report=evaluate(base,'Изменение аудиторий на 27 ноября:\n#ИОЗ_232 — занятия доц. Нидерман в ауд. 3333.\n#ИОЗ_231, #ИОЗ_241 — занятия доц. Нидерман в ауд. 3210.')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertEqual(result[0]['room'],'3210')
    def test_other_group_ignored(self):
        base=[lesson('2026-11-27','15:40')]
        result,report=evaluate(base,'#ИОЗ_232 — отмена V пары 27.11')
        self.assertEqual((result,report),(base,[]))
    def test_mixed_groups_separate(self):
        base=[lesson('2026-11-27','15:40'),lesson('2026-11-27','17:10')]
        result,report=evaluate(base,'#ИОЗ_231 — отмена V пары 27.11\n#ИЯЗ_231 — отмена VI пары 27.11')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertTrue(result[0]['cancelled']);self.assertFalse(result[1].get('cancelled'))
    def test_all_day_explicit(self):
        base=[lesson('2026-11-27',t) for t in ('15:40','17:10')]
        result,report=evaluate(base,'#ИОЗ_231 — все пары 27.11 отменены')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertTrue(all(e['cancelled'] for e in result))
    def test_ambiguous_cancel(self):
        base=[lesson('2026-11-27','15:40')]
        result,report=evaluate(base,'#ИОЗ_231 — пары 27.11 отменены')
        self.assertEqual(result,base);self.assertEqual(report[0]['status'],'review')
    def test_attachment_review(self):
        base=[lesson('2026-11-27','15:40')]
        result,report=evaluate(base,'#ИОЗ_231 — отмена V пары 27.11',attachments=[{'type':'photo'}])
        self.assertEqual(result,base);self.assertEqual(report[0]['status'],'review')
    def test_conflict_atomic(self):
        base=[lesson('2026-12-11','18:40'),lesson('2026-12-11','20:10'),lesson('2026-11-27','17:10')]
        result,report=evaluate(base,'#ИОЗ_231 — занятия доц. Нидерман перенесены с VII-VIII пары 11.12 на V-VI пары 27.11')
        self.assertEqual(result,sorted(base,key=lambda e:(e['date'],e['time'],e['subject'])))
        self.assertEqual(report[0]['status'],'review')
    def test_two_operations(self):
        base=[lesson('2026-11-27','15:40'),lesson('2026-11-27','17:10')]
        result,report=evaluate(base,'#ИОЗ_231 — отмена V пары 27.11; VI пара 27.11 будет в ауд. 3210')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertTrue(result[0]['cancelled']);self.assertEqual(result[1]['room'],'3210')
    def test_abbreviations_in_compound_bulletin(self):
        from scripts.vk_parser_v2 import clauses
        self.assertEqual(clauses('практ. занятия доц. Челноковой перенесены с 03.11 на VII пару 09.11, ауд. 3509. Практ. занятия проф. Черненькой перенесены с 03.11 на VIII пару 09.11, ауд. 3506.'),
                         ['практ. занятия доц. Челноковой перенесены с 03.11 на VII пару 09.11, ауд. 3509.', 'Практ. занятия проф. Черненькой перенесены с 03.11 на VIII пару 09.11, ауд. 3506.'])
    def test_teacher_replacement(self):
        base=[lesson('2026-11-27','15:40'),lesson('2026-11-26','17:10',teacher='Доц. А.Ю. Челнокова')]
        result,report=evaluate(base,'#ИОЗ_231 — 27.11 V пара вместо доц. Нидерман занятие проведёт доц. Челнокова')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertEqual(next(e for e in result if e['date']=='2026-11-27')['teacher'],'Доц. А.Ю. Челнокова')
    def test_relative_date(self):
        self.assertEqual(dates('завтра',STAMP),['2026-11-26'])
    def test_weekday_mismatch(self):
        base=[lesson('2026-12-11','20:10')]
        result,report=evaluate(base,'#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары в пятницу 11.12 на VIII пару в субботу 27.11.')
        self.assertEqual(result,base);self.assertEqual(report[0]['status'],'review')
    def test_subject_replacement(self):
        base=[lesson('2026-11-27','15:40')]
        result,report=evaluate(base,'#ИОЗ_231 — 27.11 V пара вместо дисциплины «Методика обучения истории» состоится «Педагогика»')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertEqual(result[0]['subject'],'Педагогика')
    def test_no_duplicate_when_excel_updated(self):
        base=[lesson('2026-11-27','20:10')]
        result,report=evaluate(base,'#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VIII пару 27.11.')
        self.assertEqual(report[0]['status'],'applicable',report)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['previous_date'],'2026-12-11')

if __name__=='__main__':unittest.main()
