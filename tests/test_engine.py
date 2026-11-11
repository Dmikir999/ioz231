"""Run without third-party dependencies: python -m unittest discover -s tests -v"""
import json
import unittest
from pathlib import Path
from scripts.engine import detect_change, apply_changes, parse_dates
from scripts.xlsx_reader import _expand_segment

ROOT=Path(__file__).resolve().parent.parent
DATA=json.loads((ROOT/'tests'/'autumn_2026.json').read_text(encoding='utf-8'))
LESSONS=DATA['entries']

class ScheduleTests(unittest.TestCase):
    def test_only_group_231(self):
        self.assertEqual(len(LESSONS),149)
        self.assertTrue(all(x['group']=='ИОЗ-231' and x['source_sheet']=='4иоз' for x in LESSONS))
        self.assertFalse(any('ИОЗ-232' in x['subject'] for x in LESSONS))

    def test_november_9_is_three_lessons(self):
        lessons=[x for x in LESSONS if x['date']=='2026-11-09']
        self.assertEqual([(x['time'],x['subject'],x['room']) for x in lessons],[
            ('17:10','История отечественной культуры','3207'),
            ('18:40','История отечественной культуры','3509'),
            ('20:10','Логика и теория аргументации','3506'),
        ])

    def test_november_11(self):
        self.assertEqual(len([x for x in LESSONS if x['date']=='2026-11-11']),4)

    def test_specific_group_notes(self):
        warnings=[]
        text='Политология (пр.) 14.09 для группы ИОЗ-232 (лк.) 28.09 Доц. А.В. Ткаченко Ауд. 3205'
        from datetime import date
        periods=[(date(2026,9,1),date(2026,12,30))]
        items=_expand_segment(text,0,'18:40','20:00',14,warnings,periods)
        self.assertEqual([(x['date'],x['kind']) for x in items],[('2026-09-28','Лекция')])
        self.assertEqual(warnings,[])

    def test_date_range_and_weekday(self):
        from datetime import date
        self.assertTrue(all(x['weekday']==date.fromisoformat(x['date']).weekday() for x in LESSONS))
        self.assertFalse(any('2026-10-06'<=x['date']<='2026-11-02' for x in LESSONS))

    def test_dates_from_vk(self):
        self.assertEqual(parse_dates('11 ноября 2026 года'),['2026-11-11'])
        self.assertEqual(parse_dates('11.11.2026'),['2026-11-11'])

    def test_safe_vk_transfer(self):
        post={'id':12,'owner_id':-2,'date':1794326400,
              'text':'ИОЗ-231 11.11.2026 перенос с 15:40 на 16:00'}
        result,notices,applied=apply_changes(LESSONS,[post])
        lesson=[x for x in result if x['date']=='2026-11-11' and x.get('previous_time')=='15:40']
        self.assertEqual(len(lesson),1)
        self.assertEqual(lesson[0]['time'],'16:00')
        self.assertEqual(len(applied),1)
        self.assertEqual(notices,[])

    def test_no_broad_cancellation(self):
        post={'id':18,'owner_id':-2,'date':1794326400,'text':'ИОЗ-231 11.11.2026 пары отменены'}
        candidate=detect_change(post)
        self.assertEqual(candidate['status'],'review')
        result,notices,applied=apply_changes(LESSONS,[post])
        self.assertEqual(len(notices),1)
        self.assertFalse(applied)
        self.assertTrue(all(not x.get('cancelled') for x in result))

    def test_different_group_excluded(self):
        post={'id':19,'owner_id':-2,'date':1794326400,'text':'ИОЗ-232 11.11.2026 отмена пары в 15:40'}
        self.assertIsNone(detect_change(post))

    def test_mixed_group_needs_review(self):
        post={'id':20,'owner_id':-2,'date':1794326400,'text':'ИОЗ-231, ИОЗ-232 11.11.2026 отмена пары в 15:40'}
        self.assertEqual(detect_change(post)['status'],'review')

    def test_attachment_needs_review(self):
        post={'id':21,'owner_id':-2,'date':1794326400,'text':'Изменения ИОЗ-231 11.11.2026 15:40',
              'attachments':[{'type':'photo'}]}
        self.assertEqual(detect_change(post)['status'],'review')

if __name__=='__main__':unittest.main()
