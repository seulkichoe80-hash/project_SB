"""Read-only HWPX structure probe, not a production parser or visual renderer."""
from pathlib import Path,PurePosixPath
from defusedxml import ElementTree as ET
import json,hashlib,zipfile,posixpath,struct,zlib

ROOT=Path(__file__).resolve().parents[2]
def verify_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('invalid PNG signature')
    offset=8;ended=False
    while offset<len(data):
        if offset+12>len(data):raise ValueError('truncated PNG')
        length=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8];end=offset+12+length
        if end>len(data):raise ValueError('truncated PNG chunk')
        body=data[offset+8:offset+8+length];crc=struct.unpack('>I',data[offset+8+length:end])[0]
        if (zlib.crc32(kind+body)&0xffffffff)!=crc:raise ValueError('invalid PNG CRC')
        ended|=kind==b'IEND';offset=end
    if not ended:raise ValueError('missing PNG IEND')
    return True
def extract(path):
    data=path.read_bytes();sha=hashlib.sha256(data).hexdigest();events=[];cells=[];anchors={}
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)>1000 or sum(i.file_size for i in infos)>200*1024*1024:raise ValueError('archive limit')
        for i in infos:
            if i.filename.startswith('/') or '..' in PurePosixPath(i.filename).parts or '\\' in i.filename:raise ValueError('unsafe ZIP path')
            if i.file_size/max(i.compress_size,1)>100:raise ValueError('archive expansion limit')
        names=set(z.namelist())
        if z.read('mimetype')!=b'application/hwp+zip':raise ValueError('invalid mimetype')
        package=ET.fromstring(z.read('Contents/content.hpf'))
        def local(e):return e.tag.rsplit('}',1)[-1]
        def resolve(href):
            if '://' in href or href.startswith('/') or '\\' in href:raise ValueError('external resource')
            options=[posixpath.normpath(posixpath.join('Contents',href)),href]
            for candidate in options:
                if not candidate.startswith('../') and candidate in names:return candidate
            raise ValueError('missing resource: '+href)
        manifest={e.attrib['id']:resolve(e.attrib['href']) for e in package.iter() if local(e)=='item' and 'id' in e.attrib}
        parts=[manifest[e.attrib['idref']] for e in package.iter() if local(e)=='itemref']
        if not parts:raise ValueError('missing spine')
        def walk(e,part,path,in_table=False):
            kind=local(e);locator={'part':part,'path':path};key=part+'#'+path;anchors[key]=e
            eid=hashlib.sha256(key.encode()).hexdigest()[:20]
            if kind=='t' and e.text:
                events.append({'element_id':eid,'type':'text','text':e.text,'source_kind':'original_text','location':locator,'in_table':in_table})
            elif kind=='img':
                ref=e.attrib.get('binaryItemIDRef')
                if not ref or ref not in manifest:raise ValueError('unresolved image')
                asset=manifest[ref];payload=z.read(asset)
                if asset.lower().endswith('.png'):verify_png(payload)
                events.append({'element_id':eid,'type':'image','source_kind':'original_image','asset_ref':asset,'asset_sha256':hashlib.sha256(payload).hexdigest(),'location':locator})
            elif kind=='tc':
                addr=next((c for c in e if local(c)=='cellAddr'),None)
                cells.append({'row':int(addr.attrib['rowAddr']) if addr is not None else None,'col':int(addr.attrib['colAddr']) if addr is not None else None,'text':''.join(x.text or '' for x in e.iter() if local(x)=='t'),'location':locator})
            counts={}
            for c in e:
                counts[c.tag]=counts.get(c.tag,0)+1
                walk(c,part,path+'/'+c.tag+'['+str(counts[c.tag])+']',in_table or kind=='tbl')
        for part in parts:
            if '/section' not in part:continue
            tree=ET.fromstring(z.read(part));walk(tree,part,'/'+tree.tag+'[1]')
        for e in events:
            located=anchors[e['location']['part']+'#'+e['location']['path']]
            if e['type']=='text' and located.text!=e['text']:raise ValueError('anchor roundtrip')
        assert sha==hashlib.sha256(path.read_bytes()).hexdigest()
        return {'sha256':sha,'spine':parts,'events':events,'cells':cells,'anchor_roundtrip_count':len(events),'visual_order':'NOT_RUN','source_unchanged':True}

if __name__=='__main__':
    fixture=ROOT/'tests/fixtures/synthetic/procedure-v2.hwpx'
    manifest=json.loads((fixture.parent/'hwpx-manifest-v2.json').read_text(encoding='utf-8'))
    result=extract(fixture)
    assert [e['text'] for e in result['events'] if e['type']=='text']==manifest['expected_text']
    assert len(result['cells'])==4
    assert sum(e['type']=='image' for e in result['events'])==1
    assert result['sha256']==manifest['sha256']
    (ROOT/'outputs/evidence/hwpx-probe-v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','scope':'library-validated full synthetic HWPX, paragraphs/table/image/XML anchors','events':len(result['events']),'cells':4,'images':1,'visual_order':'NOT_RUN','Hancom_open':'NOT_RUN'},ensure_ascii=False))
