"""Recover public Cloud Mail XLSX downloads with fresh session routing.

Only the configured public file is requested. Never replace the cache until
the caller validates the workbook and timetable. No tokens or URLs containing
temporary credentials are logged.
"""
from __future__ import annotations
import io
import json
import logging
import re
import time
import zipfile
from http.cookiejar import CookieJar
from urllib.parse import urlsplit, urlencode
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request

LOG=logging.getLogger('ioz231')
MAX_BYTES=5_000_000
UA='Mozilla/5.0 (compatible; IOZ231Schedule/3.0)'
CLOUD='https://cloud.mail.ru'
PUBLIC=re.compile(r'https://cloud\.mail\.ru/public/[\w-]+/[\w-]+')

def trusted(url):
    p=urlsplit(url)
    h=p.hostname or ''
    return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and (
        h=='cloud.mail.ru' or h.endswith('.cloud.mail.ru') or h.endswith('.datacloudmail.ru') or h=='datacloudmail.ru')

class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not trusted(newurl):raise ValueError('Недоверенный адрес перенаправления')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def session():
    return build_opener(HTTPCookieProcessor(CookieJar()),SafeRedirect())

def read(opener,url,source,limit=MAX_BYTES):
    if not trusted(url):raise ValueError('Недоверенный адрес Облака Mail')
    req=Request(url,headers={'User-Agent':UA,'Referer':source,'Accept':'*/*','Cache-Control':'no-cache','Pragma':'no-cache'})
    with opener.open(req,timeout=12) as res:
        if not trusted(res.geturl()):raise ValueError('Недоверенное перенаправление')
        blob=res.read(limit+1)
        if len(blob)>limit:raise ValueError('Ответ превышает допустимый размер')
        return blob

def hosts_from(raw):
    if isinstance(raw,dict):raw=[raw]
    if isinstance(raw,str):raw=[raw]
    if not isinstance(raw,list):return []
    out=[]
    for item in raw:
        url=item.get('url','') if isinstance(item,dict) else item
        if isinstance(url,str) and trusted(url) and not urlsplit(url).query and not urlsplit(url).fragment:
            out.append(url.rstrip('/'))
    return list(dict.fromkeys(out))

def page_hosts(page):
    # Extract the JSON value of weblink_get, not arbitrary URLs in page scripts.
    text=page.decode('utf-8',errors='replace')
    out=[]
    for match in re.finditer(r'"weblink_get"\s*:\s*',text):
        try:
            val,_=json.JSONDecoder().raw_decode(text[match.end():])
            out.extend(hosts_from(val))
        except (ValueError,TypeError):continue
    return list(dict.fromkeys(out))

def workbook(blob):
    if not blob.startswith(b'PK'):raise ValueError('Получен не XLSX')
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        files=archive.infolist()
        if len(files)>2000 or sum(x.file_size for x in files)>40_000_000:
            raise ValueError('Слишком большой распакованный XLSX')
        if not {'[Content_Types].xml','xl/workbook.xml'}.issubset(archive.namelist()):
            raise ValueError('Архив не является XLSX')
    return blob

def reason(exc):
    code=getattr(exc,'code',None)
    return f'HTTP {code}' if isinstance(code,int) else type(exc).__name__

def recover(source,*,validate=None,direct='',rounds=3,sleep=time.sleep):
    """Return a workbook accepted by validate, or fail without mutating state."""
    if not PUBLIC.fullmatch(source):raise ValueError('Некорректная публичная ссылка')
    path=source.split('/public/',1)[1]
    failures=[]
    def attempt(label,fn):
        try:return fn()
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as exc:
            failures.append(label+': '+reason(exc))
            LOG.warning('Mail recovery %s: %s',label,reason(exc))
            return None
    def accept(blob):
        blob=workbook(blob)
        if validate is not None:validate(blob)
        return blob
    for round_no in range(rounds):
        if round_no:sleep(2**round_no)
        op=session()
        page=attempt('public page',lambda:read(op,source,source))
        if page and page.startswith(b'PK'):
            result=attempt('public workbook',lambda:accept(page))
            if result:return result
        routes=page_hosts(page) if page else []
        # The public page usually includes a short-lived, share-specific route.
        # Refresh the dispatcher too, in case the page no longer embeds it.
        api=attempt('dispatcher',lambda:json.loads(read(op,CLOUD+'/api/v2/dispatcher?'+urlencode({'api':'2','build':'cloudweb-1'}),source,1_000_000)))
        if isinstance(api,dict):
            routes.extend(hosts_from((api.get('body') or {}).get('weblink_get')))
        routes=list(dict.fromkeys(routes))[:3]
        token_doc=attempt('download token',lambda:json.loads(read(op,CLOUD+'/api/v2/tokens/download',source,1_000_000)))
        body=token_doc.get('body',{}) if isinstance(token_doc,dict) else {}
        token=body.get('token') if isinstance(body,dict) else None
        if not token and isinstance(token_doc,dict):token=token_doc.get('token')
        for host in routes:
            url=host+'/'+path
            variants=[url+'?'+urlencode({'key':token}),url] if isinstance(token,str) and token else [url]
            for i,candidate in enumerate(variants):
                result=attempt('share route '+str(i+1),lambda:accept(read(op,candidate,source)))
                if result:
                    LOG.info('Mail XLSX recovered on attempt %d',round_no+1)
                    return result
        # Explicit operator-provided fallback is used only for the same source.
        if direct and round_no==0:
            result=attempt('configured direct route',lambda:accept(read(op,direct,source)))
            if result:return result
    raise RuntimeError('Облако Mail: не удалось подтвердить свежий XLSX после '+str(rounds)+' попыток ('+'; '.join(dict.fromkeys(failures))[:250]+')')
