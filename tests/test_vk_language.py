"""Field-by-field checks on real VK publications, not merely parser success."""
import json
import unittest
from pathlib import Path
from scripts.vk_language import parse_post, pair_numbers

FIXTURE=json.loads((Path(__file__).parent/'vk_real_bulletins.json').read_text(encoding='utf-8'))
# type, exact original groups, teachers, source date/pairs, destination date/pairs, rooms
# Missing information is None / []; never invent an original slot.
EXPECTED={
20471:[('transfer',['ИСТОБЩ-262'],['Жукоцкой'],'12-17',[3],'12-17',[5],['3504'])],
20470:[('transfer',['УЧИСТ-261'],['Жукоцкой'],'12-03',[2],'12-17',[3],['3504'])],
20469:[('transfer',['РУЛ-251'],['Сидоровой'],'12-09',[],'12-04',[2],[]),
       ('transfer',['РУЛ-251.3'],['Пучковой'],'12-09',[],'12-16',[2],[]),
       ('scheduled',['РЛ-221'],['Сидоровой'],None,[],'12-10',[8],[])],
20468:[('scheduled',['ИОЗ-242'],['Пучковой'],None,[],'12-16',[3,4],['3503'])],
20467:[('room',['УЧФИЛ-261.1'],['Пыхтиной'],'11-26',[],None,[],['3403'])],
20466:[('transfer',['ИЯЗ-251'],['Васильева'],'11-27',[3],'12-11',[3],['3207'])],
20465:[('transfer',['ИОЗ-231'],['Нидерман'],'12-11',[8],'11-27',[8],[]),
       ('transfer',['ИОЗ-232'],['Водолазова'],'12-11',[8],'11-27',[8],[])],
20464:[('transfer',['УЧФИЛ-261'],['Полтавец'],'12-02',[],'12-04',[4],[]),
       ('transfer',['УЧФИЛ-261'],['Райковой'],'12-02',[],'12-22',[3],[]),
       ('transfer',['УЧФИЛ-261'],['Кудекиной'],'12-02',[],'12-22',[4],[]),
       ('transfer',['УЧФИЛ-262.5'],['Щербаковой'],'12-02',[],'12-16',[1,2],[])],
20463:[('scheduled',['ИОЗ-241'],['Масловой'],None,[],'12-16',[3,4],['3509'])],
20462:[('transfer',['ИОЗ-242'],['Масловой'],'12-29',[],'12-25',[3,4],['3509'])],
20461:[('scheduled',['ИСТОБЩ-263'],['Масловой'],None,[],'12-04',[2],['3509'])],
20460:[('transfer',['ИСТ-241'],['Яковлевой'],'12-11',[4],'12-01',[4],['2310'])],
20458:[('scheduled',['ИЯЗ-221'],['Носова'],None,[],'12-09',[5,6],['3308'])],
20457:[('room',['УЧИСТ-261'],['Щербаковой'],'11-25',[],None,[],['3306']),
       ('room',['ФМК-25'],['Лапутиной'],'11-25',[],None,[],['3405']),
       ('room',['ИОЗ-242.4'],['Пучковой'],'11-25',[],None,[],['3406']),
       ('room',['ИОЗ-22'],['Нидерман'],'11-25',[],None,[],['3409'])],
20455:[('transfer',['УЧИСТ-261'],['Закирова'],'12-04',[],'12-14',[4],['3607'])],
20454:[('room',['ЗФАН-241.1','ЗФАН-242.2'],['Захаровой'],'11-24',[],None,[],['2204']),
       ('room',['ИСТ-241','ИЯЗ-221'],['Щулепниковой'],'11-24',[],None,[],['3604']),
       ('room',['ИСТ-231'],['Ерназарова'],'11-24',[],None,[],['3607'])],
20453:[('restriction',['ИСТ-251'],['Кувшиновой'],None,[],'12-17',[3],[])],
20452:[('transfer',['ИЯЗ-221'],['Носова','Пучковой'],'12-29',[],'12-08',[5,6],['3308','3304'])],
20451:[('transfer',['УЧИСТ-261'],['Челноковой'],'12-04',[],'11-30',[3],['3607'])],
20448:[('room',['ИСТОБЩ-2'],['Закирова'],'11-23',[],None,[],['3305']),
       ('room',['ИСТ-231'],['Смирновой'],'11-23',[],None,[],['3506']),
       ('room',['РУЛ-26'],['Романовой'],'11-23',[],None,[],['3607'])],
20445:[('transfer',['ИОЗ-221','ИОЗ-222'],['Набокиной'],'12-29',[],'12-21',[7,8],['3603'])],
20444:[('room',['ИСТОБЩ-263'],['Шаповаленко'],'11-21',[],None,[],['3307']),
       ('room',['ОИ-251М'],['Королева'],'11-21',[],None,[],['3306'])],
}
def snapshot(op):
    return (op['type'],op['groups'],op['teachers'],
            op['source_date'][5:] if op['source_date'] else None,op['source_pairs'],
            op['destination_date'][5:] if op['destination_date'] else None,op['destination_pairs'],op['rooms'])

class RealBulletinTests(unittest.TestCase):
    def test_all_real_fields(self):
        self.assertEqual(set(EXPECTED),{x['id'] for x in FIXTURE['posts']})
        for p in FIXTURE['posts']:
            with self.subTest(post=p['id']):
                report=parse_post(p)
                self.assertEqual(report['status'],'recognized',report)
                self.assertEqual([snapshot(op) for op in report['operations']],EXPECTED[p['id']])
    def test_review_flags(self):
        by_id={p['id']:parse_post(p) for p in FIXTURE['posts']}
        for id in (20469,20464,20452,20453,20451):
            self.assertTrue(by_id[id]['requires_review'],id)
        self.assertEqual(by_id[20468]['operations'][0]['subgroup'],'подгруппа 3')
        self.assertEqual(by_id[20460]['operations'][0]['subgroup'],'подгруппа 2')
        self.assertEqual(by_id[20457]['operations'][-1]['subgroup'],'КВ')
        self.assertTrue(any('противоречит' in f for o in by_id[20469]['operations'] for f in o['flags']))
        self.assertTrue(any('противоречит' in f for o in by_id[20464]['operations'] for f in o['flags']))
        self.assertEqual(by_id[20471]['operations'][0]['same_day_inferred'],True)
    def test_pair_range(self):
        self.assertEqual(pair_numbers('I–VIII пары'),list(range(1,9)))
        self.assertEqual(pair_numbers('1–4 пары'),[1,2,3,4])
        self.assertEqual(pair_numbers('8-й паре'),[8])
if __name__=='__main__':unittest.main()
