"""Deployment acceptance: production adapter, identity, atomicity and real cache."""
import copy
import json
import unittest
from datetime import date
from pathlib import Path
from scripts.engine import apply_changes
from scripts.vk_production import apply_verified_changes
from scripts.vk_reconcile import reconcile
from tests.test_vk_reconcile import lesson,post

ROOT=Path(__file__).resolve().parent.parent

def row(day,time,id,teacher='Доц. И.А. Нидерман',**extra):
    return dict(lesson(day,time,teacher),id=id,**extra)
def bulletin(text,ident=999,**extra):
    return dict(post(text),id=ident,**extra)

class ProductionSafetyTests(unittest.TestCase):
    def assert_rejected(self,entries,p):
        before=copy.deepcopy(entries)
        result,notices,applied=apply_verified_changes(entries,[p])
        self.assertEqual(entries,before)
        self.assertEqual(result,sorted(before,key=lambda e:(e['date'],e['time'],e['subject'])))
        self.assertFalse(applied)
        self.assertEqual(len(notices),1,notices)
        self.assertEqual(notices[0]['status'],'review')

    def test_real_cache_legacy_equivalence(self):
        base=json.loads((ROOT/'tests/vk_production_baseline.json').read_text(encoding='utf-8'))
        posts=base['posts']
        periods=[tuple(map(date.fromisoformat,p)) for p in base['semester']['periods']]
        old,old_notices,old_applied=apply_changes(base['entries'],posts,periods)
        new,notices,applied=apply_verified_changes(base['entries'],posts,periods)
        self.assertEqual(new,old)
        self.assertEqual(set(applied),set(old_applied))
        self.assertEqual({n['post_id'] for n in notices},{n['post_id'] for n in old_notices})
        self.assertEqual(len({x['id'] for x in new}),len(new))
        print('PRODUCTION_REAL_CACHE',json.dumps({'lessons':len(new),'applied':applied,'review':[{'id':n['post_id'],'reason':n['reason']} for n in notices],'same_schedule':True},ensure_ascii=False))

    def test_duplicate_and_edited_bulletins(self):
        entries=[row('2026-12-11','20:10','a')]
        first=bulletin('#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VI пару 27.11.')
        edited=dict(first,edited=1,text='#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VII пару 27.11.')
        result,notices,applied=apply_verified_changes(entries,[first,edited,first,edited])
        self.assertEqual(len(applied),1)
        self.assertFalse(notices)
        self.assertEqual((result[0]['id'],result[0]['date'],result[0]['time']),('a','2026-11-27','18:40'))

    def test_atomic_multiple_operations(self):
        entries=[row('2026-12-11','20:10','a')]
        p=bulletin('#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VII пару 27.11.\n#ИОЗ_231 — занятие доц. Несуществующего перенесено с VIII пары 11.12 на V пару 27.11.')
        self.assert_rejected(entries,p)

    def test_wrong_group_ignored(self):
        entries=[row('2026-12-11','20:10','a')]
        p=bulletin('#ИОЗ_232 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VII пару 27.11.')
        self.assertEqual(apply_verified_changes(entries,[p]),(entries,[],[]))

    def test_subgroup_blocked(self):
        self.assert_rejected([row('2026-12-11','20:10','a')],bulletin('#ИОЗ_231, подгруппа 2 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VII пару 27.11.'))

    def test_unknown_source_owner(self):
        p=bulletin('#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VII пару 27.11.',owner_id=-1)
        self.assert_rejected([row('2026-12-11','20:10','a')],p)

    def test_bad_date(self):
        self.assert_rejected([row('2026-11-27','20:10','a')],bulletin('#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 31.11 на VII пару 27.11.'))

    def test_attachment_blocked(self):
        p=bulletin('#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VII пару 27.11.',attachments=[{'type':'photo'}])
        self.assert_rejected([row('2026-12-11','20:10','a')],p)

    def test_parallel_destination_blocked(self):
        entries=[row('2026-11-27','18:40','a'),row('2026-11-27','18:40','b','Доц. А.Ю. Челнокова')]
        self.assert_rejected(entries,bulletin('#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на VII пару 27.11.'))

    def test_unknown_partial_cancel(self):
        self.assert_rejected([row('2026-11-27','18:40','a')],bulletin('#ИОЗ_231 — занятие на VII паре 27.11 отменено.'))

    def test_explicit_all_day_cancel(self):
        entries=[row('2026-11-27','18:40','a'),row('2026-11-27','20:10','b','Доц. А.Ю. Челнокова'),row('2026-12-11','20:10','c')]
        result,notices,applied=apply_verified_changes(entries,[bulletin('#ИОЗ_231 — все занятия 27.11 отменены.')])
        self.assertFalse(notices)
        self.assertEqual(len(applied),1)
        self.assertEqual({e['id'] for e in result if e.get('cancelled')},{'a','b'})

    def test_unverified_time(self):
        self.assert_rejected([row('2026-12-11','20:10','a')],bulletin('#ИОЗ_231 — занятие доц. Нидерман перенесено с VIII пары 11.12 на 03:00 27.11.'))

if __name__=='__main__':unittest.main()
