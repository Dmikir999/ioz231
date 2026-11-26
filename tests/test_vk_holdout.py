"""Independent expected fields transcribed from second batch of public posts.

Missing facts are intentionally blank; source uncertainty is not filled by guess.
Each post passes only if every operation's fields and subgroup scope match.
"""
import json
import unittest
from pathlib import Path
from scripts.vk_language import parse_post

POSTS=json.loads((Path(__file__).parent/'vk_holdout_twenty.json').read_text(encoding='utf-8'))['posts']
def e(typ,g,t,s='',sp='',d='',dp='',r='',sub=None):
    def split(v):return v.split('|') if v else []
    def nums(v):return [int(x) for x in split(v)]
    return (typ,split(g),split(t),split(s),nums(sp),split(d),nums(dp),split(r),sub)
EXPECTED={
20443:[e('room','ИЯЗ-221.1','Рубановой','11-20',r='3504'),e('room','ИОЗ-24','Нидерман','11-20',r='3405')],
20442:[e('scheduled','ЗФАН-231.2','Ковальчук',d='11-20',dp='5|6'),e('transfer','ЗФАН-231.2','Ковальчук','12-04',d='12-01',dp='7|8'),e('scheduled','ЗФАН-251.1','Ковальчук',d='11-20',dp='4'),e('scheduled','ЗФАН-242.2','Ковальчук',d='11-20',dp='2|3'),e('scheduled','ЗФАН-242.2','Борисовой',d='11-20',dp='1'),e('scheduled','ЗФАН-242.2','Носова',d='11-20',dp='4'),e('transfer','ЗФАН-242.2','Ковальчук','12-04',d='12-23',dp='3|4'),e('transfer','ЗФАН-242.2','Борисовой','12-04',d='11-26',dp='3'),e('scheduled','ЗФАН-24','Ивановой',d='11-26',dp='1')],
20440:[e('transfer','УЧФИЛ-262','Полтавец','12-05',d='12-19',dp='4'),e('transfer','УЧФИЛ-262','Федорова','11-21',d='11-30',dp='1|2'),e('transfer','УЧФИЛ-262','Федорова','11-28|12-04|12-05',d='12-07|12-14|12-21',dp='3|4'),e('transfer','РЛ-241','Полтавец','12-19',d='12-16',dp='4'),e('transfer','РУЛ-26','Васильева|Маркиной','12-01',d='12-04',dp='3|4'),e('transfer','ЗФАН-231.2','Ковальчук','11-20',d='12-01',dp='7|8'),e('transfer','ЗФАН-251.1','Ковальчук','11-20',d='12-04',dp='4'),e('transfer','ЗФАН-242.2','Ковальчук','11-20',d='12-23',dp='3|4'),e('scheduled','ЗФАН-242.2','Борисовой',d='11-20',dp='4'),e('scheduled','ЗФАН-242.2','Носова',d='11-20',dp='3')],
20429:[e('transfer','ИСТОБЩ-262','Масловой','11-19',d='12-03',dp='2',r='3509')],
20428:[e('transfer','ИЯЗ-241','Черных','11-17',d='12-17',dp='2|3',r='3409'),e('transfer','ИЯЗ-241','Питько','11-18',d='12-02',dp='1|2',r='3603'),e('transfer','ИЯЗ-241','Якушевич','11-18',d='12-08',dp='3|4'),e('transfer','ИЯЗ-241','Якушевич','12-08','3','12-22','3','3403'),e('transfer','ИЯЗ-241','Куприянова','11-17',d='12-01|12-15',dp='1|2',r='3607')],
20427:[e('transfer','ИСТОБЩ-261','Закирова','11-18',d='11-25',dp='3|4',r='3213')],
20425:[e('cancel','ЗФАН-231.2','Санчес Милагрос','11-16')],
20424:[e('room','УЧИСТ-261','Корчагиной','11-16',r='3307'),e('room','ИСТОБЩ-263','Закирова','11-16',r='3607')],
20423:[e('room','ОИ-251М','Андреева','11-14',r='3303'),e('room','ИСТОБЩ-263','Шаповаленко','11-14',r='3306'),e('room','СОРЯЛ-261М','Сидоровой','11-14',r='3507'),e('room','ИЯЗ-251','Биляловой','11-14',r='3605',sub='подгруппа 1'),e('room','ТМОИ-251М|СПТФ-251М','Корчагиной','11-14',r='3604'),e('room','ИЯЗ-221|ИЯЗ-222','Борисовой','11-14',r='3606')],
20422:[e('transfer','УЧФИЛ-262.5','Биляловой','12-23','1','11-18','4'),e('scheduled','ЗФАН-231.1','Яковлевой',d='12-25',dp='5|6'),e('scheduled','ЗФАН-241.1','Башиловой',d='12-22',dp='4')],
20417:[e('room','ИОЗ-241','Гореева','11-12',r='3210'),e('room','ИСТОБЩ-261|ИСТОБЩ-262','Водолазова','11-12',r='3305'),e('room','ИОЗ-231|ИОЗ-232','Шенер','11-12',r='3407'),e('room','ИОЗ-221|ИОЗ-22|ИЯЗ-221','Андреева','11-12',r='3606')],
20416:[e('room','ИЯЗ-241','Грибковой','11-11',r='3405'),e('room','УЧИСТ-261','Щербаковой','11-11',r='3508'),e('room','ИСТ-251','Пучковой','11-11',r='3421',sub='подгруппа 1'),e('room','ИОЗ-242','Пучковой','11-11',r='3421',sub='подгруппа 4'),e('room','ФГП-251М','Шаповала','11-11',r='3405'),e('room','ИОЗ-221|ИОЗ-222','Савиных','11-11',r='3409')],
20415:[e('scheduled','УЧИСТ-261','Закирова',d='12-04',dp='4',r='3306'),e('scheduled','УЧИСТ-261','Закирова',d='12-18',dp='4',r='3306')],
20414:[e('transfer','ОИ-251М','Малышевой','12-02',d='11-23',dp='7|8'),e('transfer','ОИ-251М','Челноковой','11-23',d='12-02',dp='6|7|8')],
20412:[e('transfer','ИОЗ-241','Звонаревой','12-29',d='12-24',dp='3|4',r='3508')],
20411:[e('transfer','ИСТОБЩ-262','Набокиной','12-09',d='12-02',dp='3|4',r='3207')],
20410:[e('transfer','ИСТОБЩ-261','Набокиной','11-11',d='12-02',dp='2',r='3207')],
20407:[e('transfer','УЧФИЛ-262','Федорова','11-14',d='11-21',dp='1|2')],
20406:[e('transfer','ИЯЗ-241','Масловой','12-01',d='12-08',dp='2',r='3509')],
20405:[e('room','РЛ-25','Калашникова','11-10',r='3205'),e('room','РУЛ-26','Райковой|Васильева','11-10',r='3205'),e('room','РЛ-24','Геймбух','11-10',r='3307'),e('room','ИСТОБЩ-261','Набокиной','11-10',r='3306'),e('room','ИСТ-251.2','Тарапаты','11-10',r='3517'),e('room','ЗФАН-241.1|ЗФАН-242|ФМК-252.2','Башиловой','11-10',r='3604')],
}
def snapshot(o):
    return (o['type'],o['groups'],o['teachers'],[x[5:] for x in o['source_dates']],o['source_pairs'],[x[5:] for x in o['destination_dates']],o['destination_pairs'],o['rooms'],o['subgroup'])
def evaluate():
    rows=[]
    for p in POSTS:
        report=parse_post(p)
        actual=[snapshot(o) for o in report['operations']]
        passed=report['status']=='recognized' and actual==EXPECTED[p['id']]
        if p['id']==20428:
            ops=report['operations']
            passed=passed and len(ops)==5 and ops[2]['kind']=='lecture' and ops[3]['kind']=='practice' and ops[4].get('destination_assignments')==[{'date':'2026-12-01','pairs':[1,2]},{'date':'2026-12-15','pairs':[1]}]
        rows.append(dict(id=p['id'],passed=passed,actual=actual if not passed else None,expected=EXPECTED[p['id']] if not passed else None,review=report['requires_review']))
    return rows

class HoldoutTests(unittest.TestCase):
    def test_strict_post_accuracy(self):
        rows=evaluate()
        print('STRICT_TWENTY '+json.dumps(rows,ensure_ascii=False))
        self.assertEqual(len(rows),20)
        self.assertGreater(sum(x['passed'] for x in rows)/len(rows),.90)
    def test_all_expected_rows_present(self):
        self.assertEqual(set(EXPECTED),{p['id'] for p in POSTS})
if __name__=='__main__':unittest.main()
