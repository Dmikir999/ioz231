import io
import json
import unittest
import zipfile
from urllib.error import HTTPError
from unittest.mock import patch
from scripts import mail_recovery as m

SOURCE='https://cloud.mail.ru/public/TKBt/bHWaZqMQA'
HOST='https://cloclo1.cloud.mail.ru/public/short/g/no'
OTHER='https://cloclo2.datacloudmail.ru/weblink/get'
def blob():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('[Content_Types].xml','x')
        z.writestr('xl/workbook.xml','x')
    return buf.getvalue()
def page(host):
    return json.dumps({'dispatcher':{'weblink_get':[{'url':host}]}}).encode()
def api(host):
    return json.dumps({'body':{'weblink_get':[{'url':host}]}}).encode()
def token():
    return b'{"body":{"token":"temporary"}}'
def missing(url):
    return HTTPError(url,404,'Not Found',{},None)

class RecoveryTests(unittest.TestCase):
    def test_share_page_recovers_old_dispatcher_404(self):
        def read(op,url,source,limit=m.MAX_BYTES):
            if url==SOURCE:return page(HOST)
            if '/dispatcher?' in url:return api(OTHER)
            if '/tokens/download' in url:return token()
            if url==HOST+'/TKBt/bHWaZqMQA?key=temporary':return blob()
            raise missing(url)
        with patch.object(m,'read',side_effect=read):
            self.assertEqual(m.recover(SOURCE,sleep=lambda _:None),blob())
    def test_refresh_session_after_all_routes_fail(self):
        sessions=[];sleeps=[]
        def start():
            sessions.append(object());return sessions[-1]
        def read(op,url,source,limit=m.MAX_BYTES):
            if url==SOURCE:return page(HOST)
            if '/dispatcher?' in url:return api(HOST)
            if '/tokens/download' in url:return token()
            if len(sessions)==1:raise missing(url)
            return blob()
        with patch.object(m,'session',side_effect=start),patch.object(m,'read',side_effect=read):
            self.assertEqual(m.recover(SOURCE,sleep=sleeps.append),blob())
        self.assertEqual(len(sessions),2);self.assertEqual(sleeps,[2])
    def test_bad_workbook_tries_alternative(self):
        def read(op,url,source,limit=m.MAX_BYTES):
            if url==SOURCE:return page(HOST)
            if '/dispatcher?' in url:return api(OTHER)
            if '/tokens/download' in url:return token()
            if url.startswith(HOST):return b'<html>Access denied</html>'
            return blob()
        with patch.object(m,'read',side_effect=read):
            self.assertEqual(m.recover(SOURCE,sleep=lambda _:None),blob())
    def test_wrong_sheet_rejected(self):
        def read(op,url,source,limit=m.MAX_BYTES):
            if url==SOURCE:return page(HOST)
            if '/dispatcher?' in url:return api(OTHER)
            if '/tokens/download' in url:return token()
            return blob()
        with patch.object(m,'read',side_effect=read):
            with self.assertRaises(RuntimeError):m.recover(SOURCE,validate=lambda _: (_ for _ in ()).throw(ValueError('Wrong sheet')),rounds=1)
    def test_all_fail_does_not_fake_success(self):
        with patch.object(m,'read',side_effect=missing(SOURCE)):
            with self.assertRaisesRegex(RuntimeError,'3 попыток'):
                m.recover(SOURCE,sleep=lambda _:None)
    def test_untrusted_routes(self):
        self.assertEqual(m.page_hosts(page('https://cloud.mail.ru.evil.example/a')),[])
        self.assertFalse(m.trusted('http://cloud.mail.ru'))
        self.assertFalse(m.trusted('https://cloud.mail.ru@evil.example'))
    def test_direct_public_workbook(self):
        with patch.object(m,'read',return_value=blob()):
            self.assertEqual(m.recover(SOURCE),blob())
    def test_zip_is_not_necessarily_excel(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('file.txt','x')
        with self.assertRaises(ValueError):m.workbook(buf.getvalue())
if __name__=='__main__':unittest.main()
