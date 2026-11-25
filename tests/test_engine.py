"""Run without third-party dependencies: python -m unittest discover -s tests -v"""
import json
import unittest
from datetime import date
from pathlib import Path
from scripts.engine import detect_change, apply_changes, parse_dates
from scripts.xlsx_reader import _expand_segment

ROOT=Path(__file__).resolve().parent.parent
DATA=json.loads((ROOT/'tests'/'autumn_2026.json').read_text(encoding='utf-8'))
LESSONS=DATA['entries']
NIEDERMAN_POST = {
    'id': 22, 'owner_id': -2, 'date': 1795593180,
    'text': '❗ #ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары в пятницу 11.12 на VIII пару в пятницу 27.11.\n\n'
            '❗ #ИОЗ_232 — занятие ст.пр. Водолазова перенесено с VIII пары в пятницу 11.12 на VIII пару в пятницу 27.11.',
}

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

    def test_numbered_vk_transfer_with_two_groups(self):
        result, notices, applied = apply_changes(LESSONS, [NIEDERMAN_POST])
        moved = [e for e in result if e.get('change_url') == 'https://vk.com/wall-2_22']
        self.assertEqual(len(moved), 1)
        self.assertEqual((moved[0]['date'], moved[0]['time'], moved[0]['end'], moved[0]['teacher']),
                         ('2026-11-27', '20:10', '21:30', 'Доц. И.А. Нидерман'))
        self.assertEqual(moved[0]['previous_date'], '2026-12-11')
        self.assertFalse(any(e['date'] == '2026-12-11' and e['time'] == '20:10' for e in result))
        self.assertEqual([e for e in result if 'Водолазов' in e['teacher']],
                         [e for e in LESSONS if 'Водолазов' in e['teacher']])
        self.assertEqual(len(result), len(LESSONS))
        self.assertEqual((notices, applied), ([], ['https://vk.com/wall-2_22']))

    def test_numbered_vk_transfer_already_in_excel(self):
        excel = [dict(e, date='2026-11-27') if e['date'] == '2026-12-11' and e['time'] == '20:10'
                 else e for e in LESSONS]
        result, notices, applied = apply_changes(excel, [NIEDERMAN_POST])
        destination = [e for e in result if e['date'] == '2026-11-27' and e['time'] == '20:10']
        self.assertEqual(len(destination), 1)
        self.assertEqual(destination[0]['change_url'], 'https://vk.com/wall-2_22')
        self.assertEqual(len(excel), len(result))
        self.assertEqual((notices, applied), ([], ['https://vk.com/wall-2_22']))

    def test_numbered_vk_transfer_with_different_day_and_time(self):
        post = dict(NIEDERMAN_POST, text='#ИОЗ_231 — занятие ст. пр. Водолазова перенесено '
                    'с VII пары 11 декабря на V пару в субботу 12.12.')
        entries = [e for e in LESSONS if e['date'] == '2026-12-11']
        result, notices, _ = apply_changes(entries, [post], [(date(2026, 11, 3), date(2026, 12, 30))])
        moved = [e for e in result if e.get('changed')]
        self.assertEqual(len(moved), 1)
        self.assertEqual((moved[0]['date'], moved[0]['weekday'], moved[0]['time'], moved[0]['end']),
                         ('2026-12-12', 5, '15:40', '17:00'))
        self.assertEqual(notices, [])

    def test_numbered_vk_transfer_for_occupied_slot_needs_review(self):
        post = dict(NIEDERMAN_POST, text='#ИОЗ_231 — занятие доц. Нидерман перенесено '
                    'с VIII пары 11.12 на VI пару 27.11.')
        before, _, _ = apply_changes(LESSONS, [])
        result, notices, applied = apply_changes(LESSONS, [post])
        self.assertEqual(result, before)
        self.assertEqual(applied, [])
        self.assertEqual(notices[0]['lesson_dates'], ['2026-11-27', '2026-12-11'])

    def test_room_bulletin_keeps_the_previous_room_and_link(self):
        entries = [{'date': '2026-11-12', 'time': time, 'subject': 'КВ Организация проектной деятельности',
                    'teacher': 'Доц. М.В. Шенер', 'room': '3503'} for time in ('18:40', '20:10')]
        post = {'id': 20417, 'owner_id': -70091881, 'date': 1794326400,
                'text': 'Изменение аудиторий на четверг, 12 ноября:\n'
                        '#ИОЗ_231, #ИОЗ_232 — занятия доц. Шенер в ауд. 3407.'}
        result, notices, applied = apply_changes(entries, [post])
        for lesson in result:
            self.assertEqual((lesson['previous_room'], lesson['room']), ('3503', '3407'))
            self.assertEqual(lesson['change_url'], 'https://vk.com/wall-70091881_20417')
        self.assertEqual((notices, applied), ([], ['https://vk.com/wall-70091881_20417']))

    def test_room_bulletin_with_no_previous_room(self):
        lesson = next(e for e in LESSONS if e['date'] == '2026-11-11' and e['time'] == '15:40')
        post = {'id': 23, 'owner_id': -2, 'date': 1794326400,
                'text': 'ИОЗ-231 11.11.2026 в 15:40 занятие будет в ауд. 3407'}
        for original_room in ('', '3407'):
            with self.subTest(original_room=original_room):
                result, notices, applied = apply_changes([dict(lesson, room=original_room)], [post])
                self.assertEqual((result[0]['previous_room'], result[0]['room']), ('', '3407'))
                self.assertEqual((notices, applied), ([], ['https://vk.com/wall-2_23']))

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
