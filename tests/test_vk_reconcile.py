import unittest
from datetime import datetime
from scripts.engine import TZ
from scripts.vk_language import parse_post
from scripts.vk_reconcile import reconcile

STAMP=int(datetime(2026,11,26,12,tzinfo=TZ).timestamp())
def post(text):
    return {'id':999,'owner_id':-70091881,'date':STAMP,'text':text}
def lesson(day,time,teacher='Доц. И.А. Нидерман'):
    return dict(group='ИОЗ-231',date=day,time=time,end='',teacher=teacher,subject='История',kind='Лекция',room='3406')

class ContextTests(unittest.TestCase):
    def test_infer_source_slot(self):
        base=[lesson('2026-12-11','20:10')]
        result,report=reconcile(base,post('#ИОЗ_231 — занятие доц. Нидерман перенесено с пятницы 11.12 на пятницу 27.11, VII пара.'))
        self.assertEqual(report['status'],'applicable',report)
        self.assertEqual((result[0]['date'],result[0]['time'],result[0]['previous_time']),('2026-11-27','18:40','20:10'))
        self.assertEqual(base[0]['date'],'2026-12-11')
    def test_do_not_guess_source(self):
        base=[lesson('2026-12-11','18:40'),lesson('2026-12-11','20:10')]
        result,report=reconcile(base,post('#ИОЗ_231 — занятие доц. Нидерман перенесено с пятницы 11.12 на пятницу 27.11, VII пара.'))
        self.assertEqual(report['status'],'review')
        self.assertEqual(result,base)
    def test_confirmation_existing_slot(self):
        base=[lesson('2026-11-27','18:40')]
        result,report=reconcile(base,post('#ИОЗ_231 — занятие доц. Нидерман пройдёт 27.11 на VII паре, ауд. 3205.'))
        self.assertEqual(report['status'],'applicable',report)
        self.assertEqual(result[0]['room'],'3205')
    def test_no_invented_new_lesson(self):
        base=[lesson('2026-11-27','18:40')]
        result,report=reconcile(base,post('#ИОЗ_231 — занятие доц. Нидерман пройдёт 27.11 на VIII паре.'))
        self.assertEqual(report['status'],'review')
        self.assertEqual(result,base)
    def test_group_scope(self):
        base=[lesson('2026-11-27','18:40')]
        result,report=reconcile(base,post('#ИОЗ_232 — занятие доц. Нидерман пройдёт 27.11 на VII паре.'))
        self.assertEqual(report['status'],'irrelevant')
        self.assertEqual(result,base)
    def test_wrong_weekday(self):
        base=[lesson('2026-12-11','20:10')]
        result,report=reconcile(base,post('#ИОЗ_231 — занятие доц. Нидерман перенесено с пятницы 11.12 на субботу 27.11, VII пара.'))
        self.assertEqual(report['status'],'review')
        self.assertEqual(result,base)
    def test_no_conflict(self):
        base=[lesson('2026-12-11','20:10'),lesson('2026-11-27','18:40',teacher='Доц. А.Ю. Челнокова')]
        result,report=reconcile(base,post('#ИОЗ_231 — занятие доц. Нидерман перенесено с 11.12 на 27.11, VII пара.'))
        self.assertEqual(report['status'],'review')
        self.assertEqual(result,base)
    def test_unknown_pair_time(self):
        base=[lesson('2026-12-11','20:10')]
        result,report=reconcile(base,post('#ИОЗ_231 — занятие доц. Нидерман перенесено с 11.12 на 27.11, III пара.'))
        self.assertEqual(report['status'],'review')
        self.assertEqual(result,base)
    def test_bare_group_and_instead(self):
        p=post('ВНИМАНИЕ! #РУЛ_26\nГруппу РУЛ-261\n27.11 (пятница) занятие доц. Нидерман пройдет на VII паре (вместо VIII)')
        r=parse_post(p)
        self.assertFalse(r['requires_review'],r)
        op=r['operations'][0]
        self.assertEqual((op['groups'],op['source_pairs'],op['source_date'],op['destination_pairs']),(['РУЛ-261'],[8],'2026-11-27',[7]))
    def test_multiple_room_clauses(self):
        r=parse_post(post('Изменение аудиторий на пятницу, 27 ноября:\n#ИОЗ_231 — занятия доц. Нидерман в ауд. 3407, занятия доц. Челноковой в ауд. 3205.'))
        self.assertFalse(r['requires_review'],r)
        self.assertEqual([x['rooms'] for x in r['operations']],[['3407'],['3205']])
if __name__=='__main__':unittest.main()
